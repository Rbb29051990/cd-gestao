# CD Gestão — v115

## Despesas por vencimento e valor da parcela

- Corrige a aba Despesas para usar `despesa_parcelas.data_vencimento` como base dos filtros de período.
- Os gráficos e totais agora somam `despesa_parcelas.valor`, evitando somar o valor total da despesa mãe em cada mês.
- A tabela Contas a pagar — parcelas pendentes agora respeita o filtro De/Até.
- O gráfico Fixa × Avulsa e os gráficos dos 3 meses anteriores agora usam as parcelas vencidas em cada mês.
- Mantém as melhorias anteriores de recorrência mensal, fechamento verde/vermelho e atalho Mês completo.
