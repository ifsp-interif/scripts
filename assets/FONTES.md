# Fontes utilizadas pelos scripts

Os arquivos de fonte **não estão versionados** (adicionados ao `.gitignore`).
Coloque os arquivos abaixo neste diretório (`assets/`) antes de executar os scripts.

## Etiquetas de credenciais (`gerar_etiquetas.py`)

| Constante em `config.py` | Arquivo esperado          | Descrição                                      |
|--------------------------|---------------------------|------------------------------------------------|
| `ETIQ_FONTE_MONO`        | `DejaVuSansMono.ttf`      | Fonte monospaced para exibir username e senha  |

**Download:** <https://dejavu-fonts.github.io/>

---

## Placas de identificação (`gerar_placas.py`)

| Constante em `config.py` | Arquivo esperado                  | Descrição                                     |
|--------------------------|-----------------------------------|-----------------------------------------------|
| `PLACA_FONTE_TITULO`     | `DK Bocadillo.ttf`                | Fonte decorativa do cabeçalho da placa        |
| `PLACA_FONTE_NOME`       | `AccanthisADFStd-Regular.ttf`     | Fonte fina para o nome do campus              |
| `PLACA_FONTE_NOME_BOLD`  | `AccanthisADFStdNo3-Bold.ttf`     | Fonte bold para o nome da equipe              |

**Downloads:**
- DK Bocadillo: <https://www.dafont.com/dk-bocadillo.font>
- Accanthis ADF Std: <https://arkandis.tuxfamily.org/adffonts.html>

---

> Para usar fontes diferentes, altere os valores das constantes correspondentes em `config.py`
> e coloque os novos arquivos `.ttf` neste diretório.
