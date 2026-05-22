from core.config import load_config, save_config
from core.prompts import list_prompts, save_prompt


def test_builtin_prompts_include_strict_json_rules_and_bilingual_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))

    prompts = list_prompts()
    organize = next(prompt for prompt in prompts if prompt["key"] == "organize")

    assert organize["name"] == "整理归类"
    assert organize["name_en"] == "Organize by Category"
    assert "{file_list}" in organize["content"]
    assert "move.from 必须" in organize["content_zh"]
    assert "文件列表中的每一个文件都必须出现在 actions 中" in organize["content_zh"]
    assert "允许的 action type 只有以下四种" in organize["content_zh"]
    assert "Return only FolderMind executable JSON" in organize["content_en"]
    assert "Every file in the file list must appear in actions" in organize["content_en"]
    assert "The only allowed action types are" in organize["content_en"]
    assert "璇" not in organize["content_zh"]


def test_builtin_prompts_localize_to_english_from_config(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    config = load_config()
    config.language = "en"
    save_config(config)

    prompts = list_prompts()
    study = next(prompt for prompt in prompts if prompt["key"] == "study")

    assert study["name"] == "Study Plan"
    assert "[File list]" in study["content"]
    assert "Organize learning materials" in study["content"]
    assert "Do not output explanations" in study["content"]


def test_study_prompt_uses_learning_material_task_in_chinese(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))

    prompts = list_prompts()
    study = next(prompt for prompt in prompts if prompt["key"] == "study")

    assert study["name"] == "学习计划"
    assert "学习资料" in study["content"]
    assert "课程" in study["content"]


def test_custom_prompt_preserves_bilingual_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))

    saved = save_prompt({
        "key": "custom-test",
        "name": "自定义",
        "content": "中文 {file_list}",
        "name_zh": "自定义",
        "name_en": "Custom",
        "content_zh": "中文 {file_list}",
        "content_en": "English {file_list}",
    })
    config = load_config()
    config.language = "en"
    save_config(config)

    custom = next(prompt for prompt in list_prompts() if prompt["key"] == saved["key"])

    assert custom["name"] == "Custom"
    assert custom["content"] == "English {file_list}"


def test_new_custom_prompt_defaults_to_strict_bilingual_template(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))

    saved = save_prompt({
        "key": "custom-empty",
        "name": "自定义",
        "content": "",
    })

    assert "{file_list}" in saved["content"]
    assert "文件列表中的每一个文件都必须出现在 actions 中" in saved["content_zh"]
    assert "Every file in the file list must appear in actions" in saved["content_en"]
    assert "create_dir、move、rename、delete_dir" in saved["content_zh"]
