import subprocess
from unittest.mock import patch

import pytest

from email_utils import send_email


def test_dry_run_simple(capsys):
    send_email("a@b.com", "Assunto", "Corpo", dry_run=True)
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "a@b.com" in out
    assert "Assunto" in out
    assert "Corpo" in out
    assert "CC:" not in out
    assert "Anexo:" not in out


def test_dry_run_with_cc(capsys):
    send_email("a@b.com", "Assunto", "Corpo", cc="c@d.com", dry_run=True)
    out = capsys.readouterr().out
    assert "CC: c@d.com" in out


def test_dry_run_with_attach(capsys, tmp_path):
    attach = tmp_path / "arquivo.pdf"
    send_email("a@b.com", "Assunto", "Corpo", attach=attach, dry_run=True)
    out = capsys.readouterr().out
    assert "Anexo:" in out
    assert str(attach) in out


def test_dry_run_cc_and_attach_together(capsys, tmp_path):
    attach = tmp_path / "arquivo.pdf"
    send_email("a@b.com", "Assunto", "Corpo", cc="c@d.com", attach=attach, dry_run=True)
    out = capsys.readouterr().out
    assert "CC: c@d.com" in out
    assert "Anexo:" in out


def test_real_send_basic():
    with patch("email_utils.subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        send_email("a@b.com", "Assunto", "Corpo")
        mock_run.assert_called_once_with(
            ["gws", "gmail", "+send", "--to", "a@b.com", "--subject", "Assunto", "--body", "Corpo"],
            capture_output=True,
            text=True,
            check=True,
        )


def test_real_send_with_cc():
    with patch("email_utils.subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        send_email("a@b.com", "Assunto", "Corpo", cc="c@d.com")
        args_list = mock_run.call_args[0][0]
        assert "--cc" in args_list
        idx = args_list.index("--cc")
        assert args_list[idx + 1] == "c@d.com"


def test_real_send_with_attach(tmp_path):
    attach = tmp_path / "arquivo.pdf"
    with patch("email_utils.subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        send_email("a@b.com", "Assunto", "Corpo", attach=attach)
        args_list = mock_run.call_args[0][0]
        assert "--attach" in args_list
        idx = args_list.index("--attach")
        assert args_list[idx + 1] == str(attach)


def test_real_send_raises_on_failure():
    with patch("email_utils.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "gws", stderr="erro")
        with pytest.raises(subprocess.CalledProcessError):
            send_email("a@b.com", "Assunto", "Corpo")
