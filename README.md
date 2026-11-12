# Voo em Números

Pontualidade e cancelamentos dos voos domésticos no Brasil, por companhia, aeroporto, rota e voo, com dados oficiais da ANAC (base Voo Regular Ativo).

Site: https://vooemnumeros.com.br

## Como funciona

- `scripts/atualizar.py` baixa cada mês novo da base VRA da ANAC e guarda um resumo por voo em `data/meses/`.
- `scripts/gerar_site.py` gera o site estático em `docs/` a partir desses resumos.
- O workflow `.github/workflows/atualizar.yml` roda todo dia, baixa o mês novo quando a ANAC publica, gera o site e publica no GitHub Pages.

No horário = chegada até 30 minutos depois do previsto, mesmo critério da ANAC.

Faz parte da Família em Números, com o Óleo em Números e o Comex em Números.
