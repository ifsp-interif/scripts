from lista_equipes_especiais import (
    Team,
    TeamGroups,
    build_summary,
    group_teams,
    render_summary,
    render_summary_markdown,
)


def _grupos_fixture() -> TeamGroups:
    teams = [
        Team(campus="Campinas", nome="Alpha", mulheres=3, apenas_ensino_medio=False),
        Team(campus="São Paulo", nome="Beta", mulheres=3, apenas_ensino_medio=False),
        Team(campus="Campinas", nome="Gamma", mulheres=1, apenas_ensino_medio=True),
        Team(campus="Campinas", nome="Delta", mulheres=None, apenas_ensino_medio=False),
        Team(campus="São Paulo", nome="Épsilon", mulheres=None, apenas_ensino_medio=False),
    ]
    return group_teams(teams)


def test_build_summary_tres_mulheres():
    summary = build_summary(_grupos_fixture())
    assert summary["Exatamente três mulheres"] == {"Campinas": 1, "São Paulo": 1}


def test_build_summary_uma_mulher():
    summary = build_summary(_grupos_fixture())
    assert summary["Exatamente uma mulher"] == {"Campinas": 1}


def test_build_summary_categoria_vazia():
    summary = build_summary(_grupos_fixture())
    assert summary["Exatamente duas mulheres"] == {}


def test_build_summary_demais():
    summary = build_summary(_grupos_fixture())
    # Delta (Campinas, sem mulheres, não ensino médio) e Épsilon (São Paulo)
    assert summary["Demais equipes"] == {"Campinas": 1, "São Paulo": 1}


def test_render_summary_cabecalho(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary(_grupos_fixture(), csv_path)
    assert "Quadro resumo — Equipes especiais" in result
    assert "Total de equipes: 5" in result


def test_render_summary_contagem_categoria(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary(_grupos_fixture(), csv_path)
    assert "Exatamente três mulheres (2)" in result
    assert "Exatamente duas mulheres (0)" in result


def test_render_summary_detalhe_campus(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary(_grupos_fixture(), csv_path)
    assert "  Campinas: 1" in result
    assert "  São Paulo: 1" in result


def test_render_summary_markdown_titulo(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary_markdown(_grupos_fixture(), csv_path)
    assert "# Quadro resumo — Equipes especiais" in result
    assert "## Exatamente três mulheres (2)" in result


def test_render_summary_markdown_categoria_vazia(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary_markdown(_grupos_fixture(), csv_path)
    assert "*(nenhuma equipe)*" in result
