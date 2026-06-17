# CD Gestão — v116

## Despesas: pagamento operacional e fechamento do mês

- Divide a área de contas em **Contas a pagar** e **Contas pagas**, lado a lado no desktop e empilhadas no celular.
- Exibe a **descrição da despesa** abaixo da categoria nas duas listas.
- O botão **Pagar** abre um modal para informar:
  - data real do pagamento;
  - forma de pagamento;
  - observação opcional.
- O cadastro de nova despesa não exige mais forma de pagamento, origem ou observação de retirada.
- A saída no caixa é criada somente ao confirmar pagamento, usando a data e forma informadas.
- Adiciona campos `forma_pagamento` e `obs_pagamento` em `despesa_parcelas` para preservar o histórico por parcela.
