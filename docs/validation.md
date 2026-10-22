# O que aconteceu nos testes

[English](validation.en.md)

Em 22/10/2026, as 15 verificações passaram localmente em um cluster kind próprio, com a aplicação e o PostgreSQL saudáveis. O relatório é [test-20261022T194213Z.json](../evidence/test-20261022T194213Z.json). A limpeza restaurou a API para duas réplicas e Mimir/Prometheus A para uma.

O resultado comprova ingestão, separação lógica dos dados dos tenants, consulta via Grafana, histórico após reinício com escritor parado, detecção de falha da aplicação e reenvio de amostras da janela de indisponibilidade curta. O parâmetro de retenção foi lido no processo ativo; exclusão de blocos após 24 horas não foi testada.

A preparação encontrou uma flag de validação inexistente e dois caminhos relativos sem permissão para o usuário sem root. Essas tentativas estão em [setup-findings.json](../evidence/setup-findings.json). A API também reiniciou durante a inicialização do banco; o script passou a aguardar o banco antes de aplicar a API. As permissões não foram ampliadas para resolver os caminhos do Mimir.

A execução no GitHub Actions é registrada separadamente quando terminar. Um workflow versionado não é, por si só, um teste aprovado no CI. Os limites de topologia, armazenamento e segurança estão no README.
