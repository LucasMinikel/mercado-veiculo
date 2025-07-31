# Projeto Microserviços de Venda de Veículos

Este projeto implementa uma plataforma online para gerenciar o processo de venda de veículos automotores, utilizando uma arquitetura de microsserviços, orquestração SAGA para transações distribuídas e implantação na Google Cloud Platform (GCP).

## Visão Geral do Projeto

A plataforma é composta pelos seguintes microsserviços:

-   **Cliente Service:** Gerencia o cadastro e as informações financeiras dos clientes (saldo em conta, limite de crédito, crédito utilizado).
-   **Veículo Service:** Gerencia o cadastro, edição e status dos veículos (disponível, reservado, vendido).
-   **Pagamento Service:** Responsável pela geração de códigos de pagamento e processamento simulado de pagamentos e reembolsos.
-   **Orquestrador Service:** Coordena o fluxo de venda de veículos como uma SAGA, garantindo a consistência transacional entre os serviços através de eventos e comandos assíncronos.

### Funcionalidades Atuais:
-   Cadastro e edição de veículos.
-   Cadastro e edição de clientes (com controle de saldo e crédito).
-   Iniciação de processo de venda de veículos através de uma SAGA transacional.
-   Reserva de crédito do cliente e reserva do veículo durante a SAGA.
-   Geração de código de pagamento e processamento do pagamento.
-   Marcação do veículo como vendido ao final da SAGA.
-   Fluxo de compensação em caso de falhas em qualquer etapa da SAGA (ex: crédito insuficiente, veículo já reservado).
-   **Funcionalidade de cancelamento de compra (em desenvolvimento/implementação final da compensação).**

### Arquitetura e Tecnologias Principais:
-   **Microsserviços:** Implementados em Python 3.11 com FastAPI e SQLAlchemy.
-   **Banco de Dados:** PostgreSQL (gerenciado via Cloud SQL no GCP, localmente via Docker).
-   **Comunicação Assíncrona:** Google Cloud Pub/Sub (com emulador para desenvolvimento local) para eventos e comandos.
-   **Orquestração de Transações Distribuídas:** Padrão SAGA (modelo Orquestrador).
-   **Infraestrutura como Código (IaC):** Terraform para provisionamento e gestão de recursos no GCP.
-   **Containerização:** Docker para empacotamento e execução dos serviços.
-   **Hosting Cloud:** Google Cloud Run para execução serverless dos microsserviços.
-   **APIs:** Google Cloud API Gateway para exposição unificada da API e roteamento de requisições.
-   **Segurança:** Google Identity-Aware Proxy (IAP) para autenticação e autorização de acesso à API pública.
-   **Repositório de Imagens:** Google Artifact Registry para armazenamento das imagens Docker.

## Etapas para Rodar o Ambiente Local

Para subir o ambiente de desenvolvimento local utilizando Docker Compose:

1.  **Pré-requisitos:**
    -   Docker e Docker Compose instalados e em execução.
    -   Python 3.11 instalado (para desenvolvimento e execução de testes fora do container).
    -   `make` instalado (opcional, mas recomendado para facilitar os comandos).
    -   Ferramentas `gcloud` e `terraform` instaladas (necessárias para deploy em cloud, mas não para o ambiente local).

2.  **Construir as imagens Docker dos serviços:**
    ```bash
    make build
    # Ou, manualmente: docker-compose build
    ```

3.  **Iniciar os serviços localmente:**
    ```bash
    make dev
    # Ou, manualmente: docker-compose up -d cliente-service veiculo-service pagamento-service orquestrador db pubsub-emulator && docker-compose logs -f cliente-service veiculo-service pagamento-service orquestrador
    ```
    Este comando irá subir todos os microsserviços, o banco de dados PostgreSQL e o emulador do Pub/Sub. Ele também exibirá os logs dos serviços em tempo real.

    Os serviços estarão disponíveis nos seguintes endereços localmente:
    -   **Cliente Service:** `http://localhost:8080`
    -   **Veículo Service:** `http://localhost:8081`
    -   **Pagamento Service:** `http://localhost:8082`
    -   **Orquestrador Service:** `http://localhost:8083`

4.  **Executar os Testes (opcional):**
    Para rodar a suíte completa de testes de integração e fluxo, certifique-se de que os serviços estão rodando (`make dev` ou `make up`):
    ```bash
    make test
    # Ou, para uma execução mais rápida (assume serviços já rodando): make test-fast
    ```

5.  **Parar e Limpar o Ambiente Local:**
    Para parar todos os serviços:
    ```bash
    make stop
    # Ou, manualmente: docker-compose down
    ```
    Para parar os serviços e remover os volumes de dados (limpar o banco de dados):
    ```bash
    make clean
    # Ou, manualmente: docker-compose down -v && docker system prune -f
    ```

## Principais Decisões Técnicas

-   **Arquitetura de Microsserviços e Padrão SAGA:** Adotada para garantir modularidade, escalabilidade e resiliência. O padrão SAGA, com orquestração centralizada, permite gerenciar transações de negócios que abrangem múltiplos serviços, garantindo a consistência mesmo em ambientes distribuídos onde transações ACID tradicionais não são viáveis.
-   **Google Cloud Pub/Sub para Comunicação Assíncrona:** Escolhido como o barramento de eventos e comandos entre os microsserviços. Proporciona forte desacoplamento, resiliência (mensagens persistidas, retries automáticos) e escalabilidade inerente, essenciais para a arquitetura orientada a eventos.
-   **GCP Cloud Run para Hosting de Microsserviços:** Uma plataforma serverless e totalmente gerenciada para contêineres. Ideal para microsserviços HTTP e listeners de Pub/Sub, pois escala de zero a N instâncias sob demanda, otimizando custos e operações.
-   **Google Cloud SQL (PostgreSQL) para Persistência:** Um serviço de banco de dados relacional totalmente gerenciado, oferecendo alta disponibilidade, backups automáticos e segurança, sem a sobrecarga operacional. A escolha do PostgreSQL é pela sua robustez e funcionalidades.
-   **Terraform para Infraestrutura como Código (IaC):** Permite automatizar o provisionamento e a gestão de toda a infraestrutura GCP de forma declarativa e versionável. Isso garante ambientes consistentes, reproduzíveis e agilidade em implantações e atualizações.
-   **API Gateway para Exposição de APIs:** Atua como um ponto de entrada unificado para todos os serviços, permitindo roteamento inteligente, agregação, e aplicação centralizada de políticas de segurança (como o IAP) e observabilidade.
-   **Google Identity-Aware Proxy (IAP) para Segurança da API Externa:** Uma camada de segurança de borda que autentica e autoriza o acesso à API exposta pelo Gateway, garantindo que apenas identidades autorizadas (Google Accounts ou Service Accounts) possam interagir com o sistema, sem a necessidade de implementar lógica de autenticação complexa nos microsserviços.
-   **Python com FastAPI e Pydantic:** Escolhido pela alta performance (comparável a Node.js e Go para APIs), facilidade de desenvolvimento, tipagem forte (com validação de dados via Pydantic), e excelente suporte a operações assíncronas (`async/await`), que são cruciais para a comunicação não bloqueante com Pub/Sub e chamadas HTTP.

## Endpoints Relevantes e Estrutura da API

A API é exposta publicamente através do **Google Cloud API Gateway**. A definição completa dos endpoints e seus parâmetros pode ser encontrada no arquivo `infrastructure/terraform/modules/gateway/openapi.yaml`.

### Endpoints Principais (acessíveis via API Gateway):

-   **Saúde do Sistema:**
    -   `GET /health`: Verifica o status de saúde geral do sistema e a conectividade com o banco de dados.

-   **Gerenciamento de Clientes:**
    -   `POST /customers`: Cria um novo registro de cliente.
    -   `GET /customers`: Lista todos os clientes cadastrados.
    -   `GET /customers/{customer_id}`: Obtém detalhes de um cliente específico pelo ID.
    -   `PUT /customers/{customer_id}`: Atualiza as informações de um cliente existente.

-   **Gerenciamento de Veículos:**
    -   `POST /vehicles`: Cria um novo registro de veículo.
    -   `GET /vehicles`: Lista todos os veículos, com opções de filtro por status (`available`, `sold`, `reserved`) e ordenação.
    -   `GET /vehicles/{vehicle_id}`: Obtém detalhes de um veículo específico pelo ID.
    -   `PUT /vehicles/{vehicle_id}`: Atualiza as informações de um veículo existente (somente se não estiver reservado ou vendido).
    -   `PATCH /vehicles/{vehicle_id}/mark_as_sold`: (Interno/SAGA) Endpoint usado pelo Orquestrador para marcar um veículo como vendido.

-   **Processo de Compra (SAGA de Venda):**
    -   `POST /purchase`: Inicia o processo de compra de um veículo. Retorna um `transaction_id` para acompanhamento.
    -   `GET /saga-states/{transaction_id}`: Permite consultar o estado atual de uma transação SAGA em andamento ou concluída.
    -   `POST /purchase/{transaction_id}/cancel`: Inicia o processo de cancelamento de uma transação de compra em andamento (com compensação de recursos).

-   **Gerenciamento de Pagamentos:**
    -   `GET /payment-codes`: Lista todos os códigos de pagamento gerados.
    -   `GET /payment-codes/{code}`: Obtém detalhes de um código de pagamento específico.
    -   `POST /payments`: Processa um pagamento utilizando um código de pagamento gerado.
    -   `GET /payments`: Lista todos os pagamentos já processados.

### Exemplo de Uso da API (com autenticação IAP)

Para interagir com a API implantada na GCP, você precisará de um token de acesso do IAP.

1.  **Autentique-se no `gcloud` CLI:**
    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

2.  **Obtenha o token de acesso do IAP:**
    ```bash
    ACCESS_TOKEN=$(gcloud auth print-access-token)
    ```

3.  **Obtenha a URL base do seu API Gateway:**
    Esta URL é um output do seu deploy Terraform. Você pode obtê-la executando:
    ```bash
    terraform output gateway_url
    ```
    Vamos assumir que o output seja `seu-gateway-url.apigateway.gcp-project.cloud.goog`.

4.  **Exemplos de requisições `curl`:**

    ```bash
    # Exemplo 1: Listar veículos
    API_GATEWAY_URL="https://$(terraform output -raw gateway_url)" # Substitua se não estiver no diretório terraform
    curl -H "Authorization: Bearer $ACCESS_TOKEN" "${API_GATEWAY_URL}/vehicles"

    # Exemplo 2: Iniciar uma nova compra (substitua customer_id e vehicle_id pelos IDs reais)
    curl -X POST "${API_GATEWAY_URL}/purchase" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{
      "customer_id": 1,
      "vehicle_id": 1,
      "payment_type": "cash"
    }'

    # Exemplo 3: Consultar o estado de uma SAGA (substitua pelo transaction_id real)
    TRANSACTION_ID="<ID_DA_SUA_TRANSACAO>"
    curl -H "Authorization: Bearer $ACCESS_TOKEN" "${API_GATEWAY_URL}/saga-states/${TRANSACTION_ID}"
    ```

---

## 6. Plano de Documentação Final

Para atender aos entregáveis solicitados, o projeto precisará de um documento PDF abrangente. Abaixo, detalho o que ainda precisa ser produzido para compor este entregável final.

**Nome do Documento Sugerido:** "Documentação Técnica da Plataforma de Venda de Veículos"

### Conteúdo Detalhado:

**1. Desenho da Arquitetura (Priorizando Serviços Serverless e Gerenciáveis da Nuvem)**
    *   **Diagrama de Visão Geral (C4 Model - Context/Container):**
        *   Representação de alto nível dos componentes do sistema (Usuários, Sistema de Vendas, Serviços Externos se houver).
        *   Detalhe dos containers (microsserviços: Cliente, Veículo, Pagamento, Orquestrador) e os principais serviços GCP utilizados (API Gateway, Pub/Sub, Cloud SQL, IAP, Artifact Registry).
        *   Indicar as principais interações e fluxos de dados entre eles.
    *   **Diagrama de Fluxo SAGA de Compra (Sequence/Activity Diagram):**
        *   **Fluxo Principal:** Passo a passo detalhado da SAGA de compra (Reserva de Crédito -> Reserva de Veículo -> Geração de Código de Pagamento -> Processamento de Pagamento -> Marcação como Vendido).
        *   **Fluxos de Compensação:** Para cada ponto de falha (ex: Crédito Insuficiente, Veículo já Reservado, Falha na Geração do Código, Falha no Pagamento), ilustrar as ações de compensação (liberações de recursos, reembolsos).
        *   **Fluxo de "Desistir da Compra" (Cancelamento):** Detalhar como o comando de cancelamento externo é processado pelo Orquestrador, e quais compensações são acionadas em cada fase possível do processo.
    *   **Diagrama de Dados (Opcional, mas recomendado):**
        *   Diagrama de Entidade-Relacionamento (ERD) simplificado mostrando as entidades principais (`Customer`, `Vehicle`, `SagaState`, `PaymentCode`, `Payment`) e suas relações.

**2. Justificativa Técnica dos Serviços Utilizados e Suas Configurações de Segurança**
    *   **Introdução:** Breve panorama da filosofia de design (microsserviços, serverless, gerenciado).
    *   **Análise por Serviço GCP:** Para cada serviço (Cloud Run, Cloud SQL, Pub/Sub, API Gateway, IAP, Artifact Registry):
        *   **Justificativa:** Por que este serviço foi escolhido para a necessidade específica (ex: escalabilidade, gerenciamento de estado, mensageria assíncrona, segurança de borda, etc.).
        *   **Configurações Chave:** Detalhar as principais configurações (`min/max instâncias` para Cloud Run, `tier/versão/SSL` para Cloud SQL, `tópicos/assinaturas` para Pub/Sub, `OpenAPI spec` para API Gateway, `authorized_users` para IAP).
        *   **Aspectos de Segurança:** Como cada serviço contribui para a postura de segurança geral (ex: criptografia de dados em trânsito e em repouso, políticas de IAM granular, gerenciamento de segredos via Secret Manager).
    *   **Padrões de Integração:** Explanar como os serviços se integram (ex: Cloud Run invocando Cloud SQL, Pub/Sub acionando Cloud Run listeners, API Gateway roteando para Cloud Run).

**3. Relatório de Segurança de Dados**
    *   **Inventário de Dados Sensíveis:**
        *   Listar todos os tipos de dados sensíveis armazenados ou processados (e.g., CPF, e-mail, telefone, placa, chassi, RENAVAM, informações de pagamento).
        *   Indicar onde cada tipo de dado é armazenado (ex: Cloud SQL, logs).
    *   **Políticas de Acesso e Tratamento:**
        *   **Acesso ao Banco de Dados:** Descrever os `Service Accounts` com acesso ao Cloud SQL e seus papéis (`roles/cloudsql.client`, `Secret Manager Secret Accessor`).
        *   **Acesso à API Pública:** Como o IAP restringe o acesso externo e quais identidades são autorizadas.
        *   **Acesso Interno Service-to-Service:** (Futura implementação) Detalhar como os serviços se autenticam e autorizam entre si (via tokens de identidade do IAM).
        *   **Controles de Mascaramento:** Explicar a implementação atual de mascaramento nas respostas da API e discutir seu propósito.
        *   **Criptografia de Dados:**
            *   **Em Trânsito:** HTTPS para a API, SSL/TLS para comunicação com o banco de dados.
            *   **Em Repouso:** Criptografia padrão do Cloud SQL para discos, e a necessidade de criptografia em nível de campo para dados específicos (com gerenciamento de chaves via Secret Manager).
        *   **Retenção e Descarte:** Políticas para retenção e eventual descarte de dados (se aplicáveis ao contexto de negócio).
    *   **Análise de Riscos e Mitigações:**
        *   Identificar riscos de segurança de dados (ex: acesso não autorizado, vazamento, manipulação).
        *   Descrever as ações de mitigação implementadas e as planejadas (ex: hardening, monitoramento de logs, auditorias).
    *   **Conformidade (Opcional):** Referenciar como a solução está em conformidade com regulamentações de proteção de dados (ex: LGPD, GDPR).

**4. Relatório Técnico da Orquestração SAGA Adotada, com Justificativa**
    *   **Conceitos de SAGA:**
        *   Explicação do problema de consistência em transações distribuídas e como a SAGA o endereça.
        *   Comparação entre SAGA de Orquestração (escolhida) e SAGA de Coreografia, justificando a escolha do modelo Orquestrador para este projeto (visibilidade, controle, complexidade de compensação).
    *   **Detalhamento da Implementação da SAGA de Compra:**
        *   **Componentes Principais:** O `Orquestrador Service` (o orquestrador) e os `Participating Services` (Cliente, Veículo, Pagamento).
        *   **Gerenciamento de Estado:** Como o `SagaStateDB` no Orquestrador rastreia o progresso da SAGA (status, passo atual, contexto).
        *   **Fluxo de Comunicação:** Como comandos são enviados (Orquestrador -> Serviço) e eventos são recebidos (Serviço -> Orquestrador) via Pub/Sub para mover a SAGA para frente.
        *   **Passos da SAGA e Ações de Compensação:** Para cada passo do fluxo de compra:
            *   Descrever o comando enviado pelo Orquestrador.
            *   Descrever o evento de sucesso recebido do serviço e a ação subsequente do Orquestrador.
            *   Descrever o evento de falha recebido do serviço e a *cadeia de compensações* acionada pelo Orquestrador (sequência de `Release` ou `Refund` commands).
        *   **Fluxo de "Desistir da Compra" (Cancelamento):**
            *   Como o endpoint `POST /purchase/{transaction_id}/cancel` é o gatilho.
            *   Como o Orquestrador avalia o estado atual da SAGA.
            *   Quais compensações são acionadas dependendo do ponto no fluxo (ex: liberar veículo se já reservado, liberar crédito se já reservado, reembolsar pagamento se já processado).
        *   **Robustez e Resiliência:** Como o Pub/Sub (garantia de entrega, retries) e o rastreamento de estado do Orquestrador contribuem para a resiliência da SAGA.
    *   **Considerações e Desafios:** Discussão sobre complexidades inerentes à SAGA (ex: eventual consistência, latência, debug), e como o projeto as aborda.
    *   **Exemplos de Mensagens:** Incluir exemplos (JSON) dos principais `Commands` e `Events` definidos em `shared/models.py`.

---