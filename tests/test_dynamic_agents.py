
import unittest
from pathlib import Path
from agents.registry import register_agent, get_agent, AGENTS, list_agents
from core.common_data_area import CommonDataArea

class TestDynamicAgents(unittest.TestCase):
    def setUp(self):
        # Clean up test agent if exists
        if 'test_agent' in AGENTS:
            del AGENTS['test_agent']

    def tearDown(self):
        if 'test_agent' in AGENTS:
            del AGENTS['test_agent']

    def test_register_agent(self):
        name = 'test_agent'
        desc = 'A test agent'
        path = 'd:/tmp/test.prompt'
        
        register_agent(name, desc, path)
        
        self.assertIn(name, AGENTS)
        agent = get_agent(name)
        self.assertEqual(agent['name'], name)
        self.assertEqual(agent['description'], desc)
        self.assertEqual(agent['prompt_path'], Path(path))

    def test_list_agents_includes_custom(self):
        name = 'test_agent'
        register_agent(name, 'desc', 'path')
        
        agents = list_agents()
        names = [a['name'] for a in agents]
        self.assertIn(name, names)

if __name__ == '__main__':
    unittest.main()
