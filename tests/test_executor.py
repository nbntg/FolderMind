import json

from core.executor import execute_plan, parse_json, preview_actions, undo_plan


def plan_from(actions):
    return parse_json(json.dumps({"actions": actions})).data


def test_parse_json_valid_and_fenced():
    raw = json.dumps({"summary": "x", "actions": [{"id": 1, "type": "create_dir", "path": "new"}]})

    result = parse_json(f"```json\n{raw}\n```")

    assert result.ok
    assert result.data.summary == "x"
    assert result.data.actions[0].path == "new"


def test_parse_target_structure_json_into_actions():
    raw = json.dumps({
        "Music_Collection": {
            "Judas_Priest (Heavy_Metal)": [
                "A Touch of Evil-Judas Priest.mp3",
                "Painkiller-Judas Priest.mp3",
            ],
            "Game_Soundtracks": ["Chippin' In-SAMURAI.mp3"],
        }
    })

    result = parse_json(raw)

    assert result.ok
    assert [action.type for action in result.data.actions] == [
        "create_dir",
        "create_dir",
        "move",
        "move",
        "create_dir",
        "move",
    ]
    assert result.data.actions[0].path == "Music_Collection"
    assert result.data.actions[1].path == "Music_Collection/Judas_Priest (Heavy_Metal)"
    assert result.data.actions[2].from_path == "A Touch of Evil-Judas Priest.mp3"
    assert result.data.actions[2].to == "Music_Collection/Judas_Priest (Heavy_Metal)/A Touch of Evil-Judas Priest.mp3"


def test_parse_file_management_summary_categories_into_actions():
    raw = json.dumps({
        "file_management_summary": {
            "total_files": 2,
            "categories": [
                {
                    "category": "健康与康复训练",
                    "description": "姿势矫正和康复训练资料",
                    "files": [
                        {"title": "8步治背痛", "filename": "8步治背痛.pdf", "size_bytes": 123},
                        {"title": "Deskbound", "filename": "Deskbound.epub", "size_bytes": 456},
                    ],
                }
            ],
        }
    })

    result = parse_json(raw)

    assert result.ok
    assert [action.type for action in result.data.actions] == ["create_dir", "move", "move"]
    assert result.data.actions[0].path == "健康与康复训练"
    assert result.data.actions[1].from_path == "8步治背痛.pdf"
    assert result.data.actions[1].to == "健康与康复训练/8步治背痛.pdf"
    assert result.data.summary == "Converted file management summary into executable actions."


def test_preview_converted_category_report_does_not_mark_existing_files_missing(tmp_path):
    (tmp_path / "8步治背痛.pdf").write_text("book")
    (tmp_path / "Deskbound.epub").write_text("book")
    raw = json.dumps({
        "file_management_summary": {
            "categories": [
                {
                    "category": "健康",
                    "files": [
                        {"filename": "8步治背痛.pdf"},
                        {"filename": "Deskbound.epub"},
                    ],
                }
            ],
        }
    })

    plan = parse_json(raw).data
    preview = preview_actions(str(tmp_path), plan)

    assert preview.missing_paths == []
    assert len(preview.lines) == 3
    assert "健康" in preview.after_tree_text


def test_parse_json_accepts_serialized_plan_aliases():
    raw = json.dumps({
        "actions": [
            {"id": 1, "type": "move", "from_path": "a.txt", "to": "dest/a.txt"},
            {"id": 2, "type": "rename", "path": ".", "from_name": "old.txt", "to": "new.txt"},
        ]
    })

    result = parse_json(raw)

    assert result.ok
    assert result.data.actions[0].from_path == "a.txt"
    assert result.data.actions[1].from_name == "old.txt"


def test_parse_json_accepts_ai_action_and_mkdir_aliases():
    raw = json.dumps({
        "summary": "x",
        "actions": [
            {"action": "mkdir", "path": "/学习资料/课程"},
            {"action": "move", "from": "a.pdf", "to": "/学习资料/课程/a.pdf"},
        ],
    })

    result = parse_json(raw)

    assert result.ok
    assert result.data.actions[0].type == "create_dir"
    assert result.data.actions[0].path == "学习资料/课程"
    assert result.data.actions[1].from_path == "a.pdf"
    assert result.data.actions[1].to == "学习资料/课程/a.pdf"


def test_parse_json_accepts_nested_action_object_shape():
    raw = json.dumps({
        "summary": "x",
        "actions": [
            {"move": {"from": "a.pdf", "to": "学习资料/a.pdf"}},
            {"mkdir": {"path": "学习资料"}},
        ],
    })

    result = parse_json(raw)

    assert result.ok
    assert result.data.actions[0].type == "move"
    assert result.data.actions[0].from_path == "a.pdf"
    assert result.data.actions[1].type == "create_dir"


def test_parse_json_autofills_missing_action_ids():
    raw = json.dumps({
        "summary": "x",
        "actions": [
            {"type": "create_dir", "path": "docs"},
            {"type": "move", "from": "a.txt", "to": "docs/a.txt"},
        ],
    })

    result = parse_json(raw)

    assert result.ok
    assert [action.id for action in result.data.actions] == [1, 2]
    assert result.data.actions[1].from_path == "a.txt"


def test_parse_json_reports_missing_required_action_fields():
    missing_type = json.dumps({"actions": [{"id": 1, "path": "docs"}]})
    missing_move_target = json.dumps({"actions": [{"id": 1, "type": "move", "from": "a.txt"}]})

    type_result = parse_json(missing_type)
    move_result = parse_json(missing_move_target)

    assert not type_result.ok
    assert type_result.error.code == "ACTION_FIELD_MISSING"
    assert "actions[1].type" in type_result.error.message
    assert not move_result.ok
    assert move_result.error.code == "ACTION_FIELD_MISSING"
    assert "actions[1].to" in move_result.error.message


def test_parse_json_accepts_category_report_json_instead_of_rejecting_it():
    raw = json.dumps({
        "file_management_summary": {
            "total_files": 16,
            "categories": [
                {
                    "category": "健康",
                    "files": [{"filename": "a.pdf", "size_bytes": 123}],
                }
            ],
        }
    })

    result = parse_json(raw)

    assert result.ok
    assert result.data.actions[0].type == "create_dir"
    assert result.data.actions[1].type == "move"


def test_parse_json_rejects_unconvertible_report_json_with_clear_reason():
    raw = json.dumps({
        "file_management_summary": {
            "total_files": 16,
            "categories": [
                {
                    "category": "健康",
                    "files": [{"title": "missing filename", "size_bytes": 123}],
                }
            ],
        }
    })

    result = parse_json(raw)

    assert not result.ok
    assert result.error.code == "UNSUPPORTED_JSON_SHAPE"
    assert "无法识别格式" in result.error.message


def test_parse_json_rejects_invalid_and_unsafe_paths():
    assert parse_json("not json").error.code == "JSON_PARSE_ERROR"
    absolute = json.dumps({"actions": [{"id": 1, "type": "move", "from": "/etc/passwd", "to": "out"}]})
    traversal = json.dumps({"actions": [{"id": 1, "type": "move", "from": "../secret", "to": "out"}]})

    assert parse_json(absolute).error.code == "ABSOLUTE_PATH_NOT_ALLOWED"
    assert parse_json(traversal).error.code == "PATH_TRAVERSAL"


def test_execute_create_move_rename_delete_and_undo(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "old.txt").write_text("rename")
    (tmp_path / "empty").mkdir()
    plan = plan_from([
        {"id": 1, "type": "create_dir", "path": "dest"},
        {"id": 2, "type": "move", "from": "a.txt", "to": "dest/a.txt"},
        {"id": 3, "type": "rename", "path": ".", "from": "old.txt", "to": "new.txt"},
        {"id": 4, "type": "delete_dir", "path": "empty"},
    ])

    result = execute_plan(str(tmp_path), plan, "auto_rename")

    assert result.success_count == 4
    assert (tmp_path / "dest" / "a.txt").exists()
    assert (tmp_path / "new.txt").exists()
    assert not (tmp_path / "empty").exists()

    undo = undo_plan(str(tmp_path), result)
    assert undo.restored_count == 4
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "old.txt").exists()
    assert (tmp_path / "empty").is_dir()


def test_undo_removes_all_nested_directories_created_by_create_dir(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    plan = plan_from([
        {"id": 1, "type": "create_dir", "path": "new/inner"},
        {"id": 2, "type": "move", "from": "a.txt", "to": "new/inner/a.txt"},
    ])

    result = execute_plan(str(tmp_path), plan, "auto_rename")
    undo = undo_plan(str(tmp_path), result)

    assert result.success_count == 2
    assert undo.restored_count == 3
    assert (tmp_path / "a.txt").exists()
    assert not (tmp_path / "new").exists()


def test_undo_skips_non_empty_created_directory_and_reports_path(tmp_path):
    plan = plan_from([
        {"id": 1, "type": "create_dir", "path": "new/inner"},
    ])

    result = execute_plan(str(tmp_path), plan, "auto_rename")
    (tmp_path / "new" / "inner" / "keep.txt").write_text("keep")
    undo = undo_plan(str(tmp_path), result)

    assert undo.skipped_count == 2
    assert (tmp_path / "new" / "inner" / "keep.txt").exists()
    skipped_paths = {item.final_path for item in undo.details if item.status == "skipped"}
    assert str(tmp_path / "new" / "inner") in skipped_paths
    assert str(tmp_path / "new") in skipped_paths


def test_delete_dir_reports_non_empty_directory_without_removing_files(tmp_path):
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "keep.txt").write_text("keep")
    plan = plan_from([{"id": 1, "type": "delete_dir", "path": "folder"}])

    result = execute_plan(str(tmp_path), plan, "auto_rename")

    assert result.error_count == 1
    assert "DIRECTORY_NOT_EMPTY" in result.results[0].message
    assert (tmp_path / "folder" / "keep.txt").exists()


def test_execute_conflict_skip_and_auto_rename(tmp_path):
    (tmp_path / "a.txt").write_text("src")
    (tmp_path / "b.txt").write_text("src2")
    (tmp_path / "dest").mkdir()
    (tmp_path / "dest" / "a.txt").write_text("existing")
    (tmp_path / "dest" / "b.txt").write_text("existing")

    skipped = execute_plan(str(tmp_path), plan_from([{"id": 1, "type": "move", "from": "a.txt", "to": "dest/a.txt"}]), "skip")
    renamed = execute_plan(str(tmp_path), plan_from([{"id": 2, "type": "move", "from": "b.txt", "to": "dest/b.txt"}]), "auto_rename")

    assert skipped.skipped_count == 1
    assert (tmp_path / "a.txt").exists()
    assert renamed.success_count == 1
    assert (tmp_path / "dest" / "b (1).txt").exists()


def test_execute_missing_parent_and_preview(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    plan = plan_from([{"id": 1, "type": "move", "from": "a.txt", "to": "missing/a.txt"}])

    preview = preview_actions(str(tmp_path), plan)
    result = execute_plan(str(tmp_path), plan, "auto_rename")

    assert preview.conflicts == []
    assert result.error_count == 1
    assert "PARENT_DIR_NOT_FOUND" in result.results[0].message


def test_preview_shows_after_tree_without_changing_disk(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "dest").mkdir()
    plan = plan_from([{"id": 1, "type": "move", "from": "a.txt", "to": "dest/a.txt"}])

    preview = preview_actions(str(tmp_path), plan)

    assert "- a.txt" in preview.before_tree_text
    assert "- a.txt" in preview.after_tree_text
    assert "dest" in preview.after_tree_text
    assert (tmp_path / "a.txt").exists()
