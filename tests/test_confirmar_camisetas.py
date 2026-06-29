import csv

from confirmar_camisetas import group_by_responsible, load_teams, render_email


def _write_csv(path, rows):
    headers = [
        "Nome da Equipe",
        "Campus",
        "Nome do Responsável pela Equipe",
        "CPF do Responsável pela Equipe",
        "Tamanho da camiseta",
        "Email do Responsável pela Equipe",
        "Nome Participante 1",
        "Prontuário",
        "CPF Participante 1",
        "Tamanho da camiseta",
        "Email Participante 1",
        "Nome Participante 2",
        "Prontuário",
        "CPF Participante 2",
        "Tamanho da camiseta",
        "Email Participante 2",
        "Nome Participante 3",
        "Prontuário",
        "CPF Participante 3",
        "Tamanho da camiseta",
        "Email Participante 3",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def test_load_teams_pairs_each_person_with_own_shirt_size(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    _write_csv(
        csv_path,
        [
            [
                "Time A",
                "São Carlos",
                "Maria Silva",
                "111",
                "M",
                "MARIA@EXAMPLE.COM",
                "Ana",
                "SC1",
                "222",
                "P",
                "ana@example.com",
                "Bruno",
                "SC2",
                "333",
                "G",
                "bruno@example.com",
                "",
                "",
                "",
                "",
                "",
            ],
        ],
    )

    teams = load_teams(csv_path)

    assert teams == [
        {
            "nome": "Time A",
            "campus": "São Carlos",
            "responsavel": {
                "nome": "Maria Silva",
                "email": "maria@example.com",
                "camiseta": "M",
            },
            "participantes": [
                {"nome": "Ana", "email": "ana@example.com", "camiseta": "P"},
                {"nome": "Bruno", "email": "bruno@example.com", "camiseta": "G"},
            ],
        }
    ]


def test_group_and_render_email_lists_all_teams_and_org_email(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    _write_csv(
        csv_path,
        [
            [
                "Time A",
                "São Carlos",
                "Maria Silva",
                "111",
                "M",
                "maria@example.com",
                "Ana",
                "SC1",
                "222",
                "P",
                "ana@example.com",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "Time B",
                "São Carlos",
                "Maria Silva",
                "111",
                "M",
                "maria@example.com",
                "Caio",
                "SC3",
                "444",
                "",
                "caio@example.com",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ],
    )

    groups = group_by_responsible(load_teams(csv_path))
    body = render_email(groups["maria@example.com"])

    assert "2 equipes" in body
    assert "Equipe Time A" in body
    assert "Equipe Time B" in body
    assert "Responsável: Maria Silva — camiseta: M" in body
    assert "Caio — camiseta: não informado" in body
    assert "interif@ifsp.edu.br" in body
    assert "o quanto antes" in body
