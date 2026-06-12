import threading
import time
import unittest

from core.channel_commands import NEW_SESSION_RESET_MESSAGE
from core.common_data_area import CommonDataArea
from core.controller import ControllerResponse
from core.conversation_context import ConversationContext
from core.conversation_manager import ConversationManager
from core.conversation_runtime import ConversationRuntime
from core.inbound_request import InboundRequest
from llm.groq_client import GroqClient
from llm.mock_client import MockLLMClient


class DummyController:
    def __init__(self, ctx: ConversationContext, tracker: dict, tracker_lock: threading.Lock) -> None:
        self.cda = ctx
        self._tracker = tracker
        self._tracker_lock = tracker_lock

    def list_active_sessions(self):
        return []

    def handle_user_message(
        self,
        message,
        files=None,
        interface='UI',
        user_id=None,
        channel_id=None,
        session_id=None,
        ui_callback=None,
        execution_metadata=None,
    ) -> ControllerResponse:
        execution_metadata = dict(execution_metadata or {})
        conversation_id = str(session_id or self.cda.conversation_id)
        start_event = execution_metadata.get('start_event')
        release_event = execution_metadata.get('release_event')
        wait_for_cancel = bool(execution_metadata.get('wait_for_cancel'))

        with self._tracker_lock:
            self._tracker['active_total'] += 1
            self._tracker['global_max'] = max(self._tracker['global_max'], self._tracker['active_total'])
            current = self._tracker['active_by_conversation'].get(conversation_id, 0) + 1
            self._tracker['active_by_conversation'][conversation_id] = current
            self._tracker['max_by_conversation'][conversation_id] = max(
                self._tracker['max_by_conversation'].get(conversation_id, 0),
                current,
            )
            self._tracker['events'].append(('start', conversation_id, str(message)))

        try:
            if callable(start_event):
                start_event()
            elif isinstance(start_event, threading.Event):
                start_event.set()

            status_cb = self.cda.get_runtime('tool_status_handler')
            if callable(status_cb):
                status_cb(f'{conversation_id}:{message}')

            trace_cb = self.cda.get_runtime('executor_trace_handler')
            if callable(trace_cb):
                trace_cb('dummy_trace', {'conversation_id': conversation_id, 'message': str(message)})

            existing = str(self.cda.get_memory('chat_history', '') or '')
            self.cda.set_memory('chat_history', existing + f'User: {message}\n')
            self.cda.set_memory('agent_activity', f'trace:{conversation_id}:{message}')

            cancel_event = self.cda.get_runtime('cancel_event')
            if wait_for_cancel:
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    if isinstance(cancel_event, threading.Event) and cancel_event.is_set():
                        return ControllerResponse(status='error', content=f'cancelled:{conversation_id}', ui_feedback=[])
                    time.sleep(0.01)
                return ControllerResponse(status='complete', content=f'timeout:{conversation_id}', ui_feedback=[])

            if isinstance(release_event, threading.Event):
                release_event.wait(timeout=2.0)

            return ControllerResponse(status='complete', content=f'{conversation_id}:{message}', ui_feedback=[])
        finally:
            with self._tracker_lock:
                self._tracker['active_total'] -= 1
                self._tracker['active_by_conversation'][conversation_id] = max(
                    0,
                    self._tracker['active_by_conversation'].get(conversation_id, 1) - 1,
                )
                self._tracker['events'].append(('end', conversation_id, str(message)))


class TestConversationManager(ConversationManager):
    def __init__(self, max_workers: int = 4) -> None:
        cda = CommonDataArea()
        cda.reset()
        super().__init__(cda, max_workers=max_workers)
        self.tracker_lock = threading.Lock()
        self.tracker = {
            'active_total': 0,
            'global_max': 0,
            'active_by_conversation': {},
            'max_by_conversation': {},
            'events': [],
        }

    def _create_runtime(self, conversation_id: str, interface: str, user_id: str) -> ConversationRuntime:
        ctx = ConversationContext(self.app_cda, conversation_id)
        ctx.set_runtime('cancel_event', threading.Event())
        controller = DummyController(ctx, self.tracker, self.tracker_lock)
        return ConversationRuntime(
            conversation_id=conversation_id,
            interface=interface,
            user_id=user_id,
            cda=ctx,
            router=None,
            executor=None,
            controller=controller,
        )


class ConversationManagerIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = TestConversationManager(max_workers=4)

    def tearDown(self) -> None:
        self.manager.shutdown()
        CommonDataArea.reset()

    def test_same_conversation_requests_are_serialized(self) -> None:
        first_started = threading.Event()
        second_started = threading.Event()
        first_release = threading.Event()
        first_done = threading.Event()
        second_done = threading.Event()
        completions = []

        self.manager.submit(
            InboundRequest(
                conversation_id='telegram:chat-1',
                interface='Telegram',
                user_id='u1',
                message='first',
                execution_metadata={'start_event': first_started, 'release_event': first_release},
                completion_callback=lambda result: (completions.append(result.content), first_done.set()),
            )
        )
        self.assertTrue(first_started.wait(timeout=1.0))

        self.manager.submit(
            InboundRequest(
                conversation_id='telegram:chat-1',
                interface='Telegram',
                user_id='u1',
                message='second',
                execution_metadata={'start_event': second_started},
                completion_callback=lambda result: (completions.append(result.content), second_done.set()),
            )
        )

        self.assertFalse(second_started.wait(timeout=0.2))
        first_release.set()
        self.assertTrue(first_done.wait(timeout=1.0))
        self.assertTrue(second_started.wait(timeout=1.0))
        self.assertTrue(second_done.wait(timeout=1.0))
        self.assertEqual(self.manager.tracker['max_by_conversation'].get('telegram:chat-1'), 1)
        self.assertEqual(completions, ['telegram:chat-1:first', 'telegram:chat-1:second'])

    def test_different_conversations_run_in_parallel(self) -> None:
        first_started = threading.Event()
        second_started = threading.Event()
        release = threading.Event()
        first_done = threading.Event()
        second_done = threading.Event()

        self.manager.submit(
            InboundRequest(
                conversation_id='telegram:chat-1',
                interface='Telegram',
                user_id='u1',
                message='first',
                execution_metadata={'start_event': first_started, 'release_event': release},
                completion_callback=lambda result: first_done.set(),
            )
        )
        self.manager.submit(
            InboundRequest(
                conversation_id='telegram:chat-2',
                interface='Telegram',
                user_id='u2',
                message='second',
                execution_metadata={'start_event': second_started, 'release_event': release},
                completion_callback=lambda result: second_done.set(),
            )
        )

        self.assertTrue(first_started.wait(timeout=1.0))
        self.assertTrue(second_started.wait(timeout=1.0))
        self.assertGreaterEqual(self.manager.tracker['global_max'], 2)
        release.set()
        self.assertTrue(first_done.wait(timeout=1.0))
        self.assertTrue(second_done.wait(timeout=1.0))

    def test_cancel_is_scoped_to_one_conversation(self) -> None:
        first_started = threading.Event()
        second_started = threading.Event()
        second_release = threading.Event()
        done = {}
        first_done = threading.Event()
        second_done = threading.Event()

        self.manager.submit(
            InboundRequest(
                conversation_id='ui:chat:A',
                interface='UI',
                user_id='u1',
                message='cancel-me',
                execution_metadata={'start_event': first_started, 'wait_for_cancel': True},
                completion_callback=lambda result: (done.setdefault('A', result), first_done.set()),
            )
        )
        self.manager.submit(
            InboundRequest(
                conversation_id='ui:chat:B',
                interface='UI',
                user_id='u2',
                message='keep-going',
                execution_metadata={'start_event': second_started, 'release_event': second_release},
                completion_callback=lambda result: (done.setdefault('B', result), second_done.set()),
            )
        )

        self.assertTrue(first_started.wait(timeout=1.0))
        self.assertTrue(second_started.wait(timeout=1.0))
        self.assertTrue(self.manager.cancel('ui:chat:A'))
        second_release.set()
        self.assertTrue(first_done.wait(timeout=1.0))
        self.assertTrue(second_done.wait(timeout=1.0))
        self.assertEqual(done['A'].status, 'error')
        self.assertEqual(done['A'].content, 'cancelled:ui:chat:A')
        self.assertEqual(done['B'].status, 'complete')
        self.assertEqual(done['B'].content, 'ui:chat:B:keep-going')

    def test_history_hydration_stays_local_to_runtime(self) -> None:
        self.manager.hydrate_ui_history('ui:chat:42', 'u42', 'User: hello\n', 'trace', 42)
        runtime = self.manager.get_or_create_runtime('ui:chat:42', 'UI', 'u42')

        self.assertEqual(runtime.cda.get_memory('chat_history'), 'User: hello\n')
        self.assertEqual(runtime.cda.get_memory('agent_activity'), 'trace')
        self.assertEqual(runtime.cda.get_memory('current_chat_id'), 42)
        self.assertEqual(self.manager.app_cda.get_memory('chat_history', ''), '')
        self.assertEqual(self.manager.app_cda.get_memory('agent_activity', ''), '')

    def test_history_hydration_can_target_web_runtime(self) -> None:
        self.manager.hydrate_ui_history('web:chat:42', 'u42', 'User: hello\n', 'trace', 42, interface='WEB')
        runtime = self.manager.get_or_create_runtime('web:chat:42', 'WEB', 'u42')

        self.assertEqual(runtime.interface, 'WEB')
        self.assertEqual(runtime.cda.get_memory('chat_history'), 'User: hello\n')
        self.assertEqual(runtime.cda.get_memory('agent_activity'), 'trace')
        self.assertEqual(runtime.cda.get_memory('current_chat_id'), 42)

    def test_refresh_llm_clients_updates_existing_runtime(self) -> None:
        cda = CommonDataArea()
        cda.reset()
        cda.set_setting('llm_provider', 'mock')
        manager = ConversationManager(cda, max_workers=1)
        try:
            runtime = manager.get_or_create_runtime('conv-refresh', 'UI', 'user-1')
            self.assertIsInstance(runtime.cda.get_runtime('llm_client'), MockLLMClient)

            cda.set_setting('llm_provider', 'groq')
            refreshed = manager.refresh_llm_clients()

            self.assertEqual(refreshed, 1)
            self.assertIsInstance(runtime.cda.get_runtime('llm_client'), GroqClient)
        finally:
            manager.shutdown()

    def test_new_command_resets_channel_runtime_and_suppresses_stale_completion(self) -> None:
        first_started = threading.Event()
        first_done = threading.Event()
        reset_done = threading.Event()
        fresh_done = threading.Event()
        completions = []

        self.manager.submit(
            InboundRequest(
                conversation_id='telegram:chat-1',
                interface='Telegram',
                user_id='u1',
                message='first',
                execution_metadata={'start_event': first_started, 'wait_for_cancel': True},
                completion_callback=lambda result: (completions.append(('first', result.content)), first_done.set()),
            )
        )
        self.assertTrue(first_started.wait(timeout=1.0))

        self.manager.submit(
            InboundRequest(
                conversation_id='telegram:chat-1',
                interface='Telegram',
                user_id='u1',
                message='/new\r\n',
                completion_callback=lambda result: (completions.append(('reset', result.content)), reset_done.set()),
            )
        )

        self.assertTrue(reset_done.wait(timeout=1.0))
        self.assertEqual(self.manager.size(), 0)
        self.assertFalse(first_done.wait(timeout=0.3))

        self.manager.submit(
            InboundRequest(
                conversation_id='telegram:chat-1',
                interface='Telegram',
                user_id='u1',
                message='fresh',
                completion_callback=lambda result: (completions.append(('fresh', result.content)), fresh_done.set()),
            )
        )

        self.assertTrue(fresh_done.wait(timeout=1.0))
        self.assertEqual(
            completions,
            [
                ('reset', NEW_SESSION_RESET_MESSAGE),
                ('fresh', 'telegram:chat-1:fresh'),
            ],
        )

    def test_new_command_is_supported_for_whatsapp_conversations(self) -> None:
        done = threading.Event()
        results = []

        self.manager.submit(
            InboundRequest(
                conversation_id='whatsapp:sender-1',
                interface='WhatsApp',
                user_id='u1',
                message='/new',
                completion_callback=lambda result: (results.append(result.content), done.set()),
            )
        )

        self.assertTrue(done.wait(timeout=1.0))
        self.assertEqual(results, [NEW_SESSION_RESET_MESSAGE])
        self.assertEqual(self.manager.size(), 0)

    def test_channel_request_inherits_app_trace_handler_when_request_trace_missing(self) -> None:
        done = threading.Event()
        traces = []

        def _trace(event_type, payload):
            traces.append((str(event_type), dict(payload or {})))

        self.manager.app_cda.set_runtime('executor_trace_handler', _trace)
        self.manager.submit(
            InboundRequest(
                conversation_id='whatsapp:sender-1',
                interface='WhatsApp',
                user_id='u1',
                message='hello from whatsapp',
                completion_callback=lambda result: done.set(),
            )
        )

        self.assertTrue(done.wait(timeout=1.0))
        self.assertTrue(any(evt == 'dummy_trace' for evt, _ in traces))


if __name__ == '__main__':
    unittest.main()
