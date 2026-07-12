import os
import tempfile

import openpyxl

from core.common_data_area import CommonDataArea
from tools.tool_registry import call_tool, get_tool


def test_tools_enforce_accessible_directories():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as other:
        cda.set_setting('accessible_directories', [allowed])

        ok = call_tool('list_directory', {'directory_path': allowed})
        assert ok['success'] is True

        denied = call_tool('list_directory', {'directory_path': other})
        assert denied['success'] is False


def test_read_inspect_copy_move_within_bounds():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as allowed:
        cda.set_setting('accessible_directories', [allowed])

        file_path = os.path.join(allowed, 'sample.txt')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('hello world')

        inspect = call_tool('inspect_file', {'file_path': file_path})
        assert inspect['success'] is True
        assert inspect['data']['extension'] == '.txt'

        read = call_tool('read_file', {'file_path': file_path})
        assert read['success'] is True
        assert 'hello world' in read['data']['content']

        copy_path = os.path.join(allowed, 'copy.txt')
        copied = call_tool('copy_file', {'source_path': file_path, 'destination_path': copy_path})
        assert copied['success'] is True
        assert os.path.exists(copy_path)

        move_path = os.path.join(allowed, 'moved.txt')
        moved = call_tool('move_file', {'source_path': copy_path, 'destination_path': move_path})
        assert moved['success'] is True
        assert os.path.exists(move_path)
        assert not os.path.exists(copy_path)


def test_no_delete_tool_exists():
    assert get_tool('delete') is None


def test_read_file_extracts_xlsx_rows():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as allowed:
        cda.set_setting('accessible_directories', [allowed])

        file_path = os.path.join(allowed, 'employees.xlsx')
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = 'Employees'
        worksheet.append(['Name', 'Email', 'Phone'])
        worksheet.append(['Jishnu Haridas', 'jishnu@example.com', '919847760326'])
        workbook.save(file_path)

        read = call_tool('read_file', {'file_path': file_path})

        assert read['success'] is True
        assert read['data']['type'] == 'xlsx'
        assert 'Sheet: Employees' in read['data']['content']
        assert 'Name | Email | Phone' in read['data']['content']
        assert 'Jishnu Haridas | jishnu@example.com | 919847760326' in read['data']['content']
