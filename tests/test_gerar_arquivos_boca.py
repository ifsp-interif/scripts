from gerar_arquivos_boca import build_usuarios
from interif_core import CredencialEquipe


def _user_blocks(usuarios_txt: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for line in usuarios_txt.splitlines():
        if not line or line == "[user]":
            continue
        key, value = line.split(" = ", 1)
        if key == "usernumber" and current:
            blocks.append(current)
            current = {}
        current[key] = value

    if current:
        blocks.append(current)

    return blocks


def test_teams_disable_multilogin_and_other_users_keep_it_enabled():
    credenciais = [
        CredencialEquipe(
            campus="São Paulo",
            sigla="SPO",
            label="São Paulo",
            nome_equipe="Equipe A",
            username="teamspo1",
            password="senha1",
            coord_nome="Coord",
            coord_email="coord@example.com",
            resp_nome="Resp",
            resp_email="resp@example.com",
        )
    ]
    info_campus = [
        {
            "campus": "São Paulo",
            "sigla": "SPO",
            "prefixo": "spo",
            "n_equipes": 1,
            "bloco_inicio": 1001,
            "bloco_fim": 1001,
        }
    ]

    usuarios_txt = build_usuarios(credenciais, info_campus, ano=2026)

    multilogin_by_type = {
        block["usertype"]: block["usermultilogin"] for block in _user_blocks(usuarios_txt)
    }
    assert multilogin_by_type == {
        "team": "f",
        "staff": "t",
        "judge": "t",
        "score": "t",
    }
