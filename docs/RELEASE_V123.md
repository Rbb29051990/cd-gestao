# Release V123 — Dashboard Executivo Compacto

## Principais alterações

- Novo dashboard executivo em 3 linhas, focado em decisões financeiras, comerciais e de estoque.
- Linha 1 compacta com KPIs: Faturamento Bruto, Total de Taxas, Faturamento Líquido, Total de Despesas, Lucro Líquido, Margem Líquida e Ticket Médio.
- Linha 2 reorganizada com gráficos compactos de Faturamento Bruto, Faturamento Líquido, Despesas Fixas x Avulsas, Lucro Líquido, Taxas por Forma de Pagamento e Top 5 Categorias.
- Linha 3 com Ranking de Vendedoras, Estoque Parado e Top 5 Clientes.
- Ranking de vendedoras calculado por valor líquido da venda, descontando taxas quando aplicável.
- Top 5 clientes com valor líquido, peças, ticket médio e última compra.
- Rodapé com alertas inteligentes de crescimento e pontos de atenção.

## Observações técnicas

- Clientes cadastrados por vendedora fica zerado no ranking enquanto não houver vínculo direto entre cadastro de cliente e vendedora no schema atual.
- O dashboard mantém o filtro padrão de período por data inicial e final.
- A tendência mensal utiliza até 12 meses com base no mês final selecionado.
