#!/usr/bin/env python3
"""Lista equipes cujo coach possui email @aluno.ifsp.edu.br."""

import argparse

from inscricoes_atuais import CSV_FILE, load_teams


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=CSV_FILE, metavar="ARQUIVO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    teams = load_teams(args.csv)

    flagged = [t for t in teams if "@aluno.ifsp.edu.br" in t["resp_email"]]

    if not flagged:
        print("Nenhuma equipe com coach de email @aluno.ifsp.edu.br encontrada.")
        return

    print(f"{len(flagged)} equipe(s) com coach de email @aluno.ifsp.edu.br:\n")
    for t in sorted(flagged, key=lambda t: (t["campus"], t["equipe"])):
        print(f"  Campus : {t['campus']}")
        print(f"  Equipe : {t['equipe']}")
        print(f"  Coach  : {t['resp_nome']} <{t['resp_email']}>")
        print()


if __name__ == "__main__":
    main()
