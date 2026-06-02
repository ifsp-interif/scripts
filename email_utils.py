"""Envio de e-mail via gws gmail +send — utilitário compartilhado pelos scripts InterIF."""

import subprocess
from pathlib import Path


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    cc: str | None = None,
    attach: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Envia um e-mail via `gws gmail +send`. Em dry_run, imprime em vez de enviar."""
    if dry_run:
        print(f"\n--- DRY-RUN: email para {to} ---")
        print(f"Assunto: {subject}")
        if cc:
            print(f"CC: {cc}")
        if attach:
            print(f"Anexo: {attach}")
        print()
        print(body)
        print("--- fim do email ---")
        return

    cmd = ["gws", "gmail", "+send", "--to", to, "--subject", subject, "--body", body]
    if cc:
        cmd += ["--cc", cc]
    if attach:
        cmd += ["--attach", str(attach)]

    print(f"  → Enviando para {to} ...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("    OK: enviado")
        if result.stdout.strip():
            print(result.stdout.strip())
    except subprocess.CalledProcessError as exc:
        print("    ERRO: envio falhou")
        if exc.stdout:
            print(exc.stdout.strip())
        if exc.stderr:
            print(exc.stderr.strip())
        raise
