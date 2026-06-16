# CD Gestão — v113

## Despesas recorrentes e fechamento mensal

- Despesa fixa sem parcelamento pode ser marcada como recorrente.
- Ao salvar, o sistema gera 12 contas a pagar mensais em aberto.
- O vencimento dos meses seguintes mantém o mesmo dia informado, ajustando para o último dia do mês quando necessário.
- Despesa parcelada não pode ser recorrente: o campo é ocultado automaticamente.
- Novo gráfico de fechamento mensal em despesas: verde para pagas e vermelho para a pagar.
- Cada lançamento recorrente pode ter valor e vencimento ajustados individualmente antes do pagamento.

## Observação operacional

A recorrência automatiza a criação das contas, não o pagamento. A saída no caixa só ocorre quando a parcela/conta é marcada como paga.
