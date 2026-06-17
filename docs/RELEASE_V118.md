# RELEASE V118

## Ajustes Financeiros

Nova opção no menu Financeiro: **Ajustes**.

Permite lançar entradas avulsas no caixa para implantação no meio do mês e correções futuras.

### Tipos disponíveis
- Saldo Inicial
- Ajuste de Caixa
- Recebimento Avulso
- Aporte dos Sócios
- Transferência
- Outros

### Campos
- Data
- Tipo
- Descrição
- Forma de Pagamento
- Valor
- Observação opcional

### Integração
Cada ajuste gera automaticamente uma entrada na tabela `caixa`, mantendo histórico próprio na tabela `ajustes_financeiros`.

### Segurança
A exclusão de ajustes fica restrita ao Administrador N1 e remove também a movimentação correspondente no caixa.
