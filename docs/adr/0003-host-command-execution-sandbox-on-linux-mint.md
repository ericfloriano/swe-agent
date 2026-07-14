# Execução de Comandos com Isolamento em Nível de Host no Linux Mint

Decidimos executar operacoes locais do backend diretamente no host Linux Mint, descartando containers Docker para manter o projeto simples e demonstrável em hardware limitado. Para garantir segurança, o sistema:

* restringe escrita/leitura ao workspace ativo;
* valida caminhos com `pathlib.Path.resolve()` contra Path Traversal;
* aplica lista negra para termos perigosos como `sudo`, `rm`, `mkfs`, `format` e similares;
* mantém comandos permitidos restritos a operações necessárias como Git, Python e pytest opcional.

O workflow padrão atual não executa testes automaticamente. `pytest` permanece permitido apenas para validações manuais ou futuras extensões.
