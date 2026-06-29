import argparse

import pytest

from enviar_credenciais import grupos_envio, validar_opcoes
from gerar_arquivos_boca import (
    build_score,
    build_secrets,
    build_toml,
    build_usuarios,
    build_usuarios_fase2,
    gerar_credenciais_fase2,
)
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


def test_fase2_generates_global_team_usernames_in_csv_order():
    teams = [
        {
            "campus": "São Paulo",
            "nome_equipe": f"Equipe {i:03d}",
            "coord_nome": "Coord",
            "coord_email": "coord@example.com",
            "resp_nome": "Resp",
            "resp_email": "resp@example.com",
        }
        for i in range(1, 101)
    ]
    campi = {"São Paulo": "SPO"}

    credenciais, info_campus = gerar_credenciais_fase2(teams, campi)

    assert credenciais[0].username == "team01"
    assert credenciais[1].username == "team02"
    assert credenciais[98].username == "team99"
    assert credenciais[99].username == "team100"
    assert info_campus == [
        {
            "campus": "São Paulo",
            "sigla": "SPO",
            "prefixo": "spo",
            "n_equipes": 100,
            "bloco_inicio": 1001,
            "bloco_fim": 1100,
        }
    ]


def test_fase2_usuarios_has_one_staff_one_judge_one_score_and_multilogin_rules():
    credenciais = [
        CredencialEquipe(
            campus="São Paulo",
            sigla="SPO",
            label="São Paulo",
            nome_equipe="Equipe A",
            username="team01",
            password="senha1",
            coord_nome="Coord",
            coord_email="coord@example.com",
            resp_nome="Resp",
            resp_email="resp@example.com",
        ),
        CredencialEquipe(
            campus="Campinas",
            sigla="CMP",
            label="Campinas",
            nome_equipe="Equipe B",
            username="team02",
            password="senha2",
            coord_nome="Coord",
            coord_email="coord@example.com",
            resp_nome="Resp",
            resp_email="resp@example.com",
        ),
    ]

    usuarios_txt = build_usuarios_fase2(credenciais, ano=2026)
    blocks = _user_blocks(usuarios_txt)

    assert [block["username"] for block in blocks] == [
        "team01",
        "team02",
        "staffif",
        "judgeif",
        "scoreif",
    ]
    assert [block["usertype"] for block in blocks].count("staff") == 1
    assert [block["usertype"] for block in blocks].count("judge") == 1
    assert [block["usertype"] for block in blocks].count("score") == 1
    assert {
        block["username"]: block["usermultilogin"] for block in blocks
    } == {
        "team01": "f",
        "team02": "f",
        "staffif": "t",
        "judgeif": "t",
        "scoreif": "t",
    }


def test_fase2_site_files_do_not_include_campus_sections():
    info_campus = [
        {
            "campus": "São Paulo",
            "sigla": "SPO",
            "prefixo": "spo",
            "n_equipes": 2,
            "bloco_inicio": 1001,
            "bloco_fim": 1002,
        },
        {
            "campus": "Campinas",
            "sigla": "CMP",
            "prefixo": "cmp",
            "n_equipes": 1,
            "bloco_inicio": 1003,
            "bloco_fim": 1003,
        },
    ]

    toml_txt = build_toml(info_campus, separar_campi=False)
    score_txt = build_score(info_campus, separar_campi=False)
    secrets_txt = build_secrets(info_campus, separar_campi=False)

    assert toml_txt.count("[[sedes]]") == 1
    assert 'name = "SPO"' not in toml_txt
    assert 'codes = ["teamspo"]' not in toml_txt
    assert score_txt == "GERAL 1001/1003/1 # /^team/ /^score/ /^judge/ /^admin/\n"
    assert secrets_txt.count("[[secrets]]") == 1
    assert 'name = "SPO"' not in secrets_txt
    assert 'secret = "spo_abc"' not in secrets_txt


def test_fase2_blocks_staff_credentials_sending():
    args = argparse.Namespace(
        fase=2,
        enviar_staff=True,
        so_coordenadores=False,
        so_responsaveis=False,
        so_participantes=False,
    )

    with pytest.raises(ValueError, match="não devem ser enviadas"):
        validar_opcoes(args)


def test_fase2_default_sends_only_responsibles_and_participants():
    args = argparse.Namespace(
        fase=2,
        so_coordenadores=False,
        so_responsaveis=False,
        so_participantes=False,
    )

    assert grupos_envio(args) == (False, True, True, False)


def test_fase2_blocks_local_coordinator_sending():
    args = argparse.Namespace(
        fase=2,
        enviar_staff=False,
        so_coordenadores=True,
        so_responsaveis=False,
        so_participantes=False,
    )

    with pytest.raises(ValueError, match="coordenadores locais"):
        validar_opcoes(args)
