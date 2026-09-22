import pytest
from parcours.core.vocab import load_vocab, is_valid_value, VocabError


def test_loads_named_lists(tmp_path):
    path = tmp_path / "vocab.yaml"
    path.write_text("widget_status: [draft, published]\ncolor: [red, blue]\n")

    vocab = load_vocab(path)

    assert vocab == {"widget_status": ["draft", "published"], "color": ["red", "blue"]}


def test_rejects_non_list_entries(tmp_path):
    path = tmp_path / "vocab.yaml"
    path.write_text("widget_status: not-a-list\n")

    with pytest.raises(VocabError):
        load_vocab(path)


def test_is_valid_value_true_and_false():
    vocab = {"widget_status": ["draft", "published"]}
    assert is_valid_value(vocab, "widget_status", "draft") is True
    assert is_valid_value(vocab, "widget_status", "archived") is False


def test_is_valid_value_raises_for_unknown_vocab_name():
    vocab = {"widget_status": ["draft"]}
    with pytest.raises(VocabError):
        is_valid_value(vocab, "nonexistent", "draft")
