# Mercado Veículo - API Backend (Saga Microservices)

Este projeto implementa o backend de uma plataforma de revenda de veículos, focando na gestão de clientes, veículos, pagamentos e orquestração de processos de compra via transações distribuídas (Saga). A API é desenvolvida para ser consumida por uma aplicação frontend.

## Visão Geral do Projeto

O objetivo principal é criar uma API robusta e escalável que gerencie o ciclo de vida de um veículo desde o cadastro até a venda. As funcionalidades chave incluem:

*   **Cadastro e Gestão de Veículos:** Adicionar novos veículos à venda, editar suas informações e marcar como vendidos.
*   **Cadastro e Gestão de Clientes:** Registrar compradores, gerenciar seus dados e limites de crédito.
*   **Processo de Venda de Veículos:** Um fluxo transacional complexo que envolve a seleção, reserva, pagamento e baixa do veículo no estoque. Este processo é tratado como uma [Saga Distribuída](#padrão-saga-orquestrador).
*   **Listagens:** Visualização de veículos à venda e veículos já vendidos.

## Arquitetura da Solução

A solução é construída com base em uma arquitetura de microsserviços, utilizando comunicação assíncrona e o padrão Saga para garantir a consistência das transações distribuídas.

### Componentes Principais

O sistema é composto pelos seguintes microsserviços:

*   **`cliente-service`**:
    *   **Responsabilidade**: Gerencia o cadastro de clientes, seus dados pessoais (nome, email, telefone, documento), limite de crédito e crédito disponível.
    *   **Tecnologias**: FastAPI, SQLAlchemy (PostgreSQL).
    *   **Endpoints Expostos**: `/customers`, `/health`.
    *   **Comunicação (Pub/Sub)**: Responde a comandos de reserva (`commands.credit.reserve`) e liberação (`commands.credit.release`) de crédito, e publica eventos de sucesso (`events.credit.reserved`, `events.credit.released`) ou falha (`events.credit.reservation_failed`).

*   **`veiculo-service`**:
    *   **Responsabilidade**: Gerencia o cadastro de veículos (marca, modelo, ano, cor, preço, placa, **número do chassi, RENAVAM**), e controla o status de reserva e venda (`is_reserved`, `is_sold`).
    *   **Tecnologias**: FastAPI, SQLAlchemy (PostgreSQL).
    *   **Endpoints Expostos**: `/vehicles`, `/health`, `/vehicles/{id}/mark_as_sold`.
    *   **Comunicação (Pub/Sub)**: Responde a comandos de reserva (`commands.vehicle.reserve`) e liberação (`commands.vehicle.release`) de veículos, e publica eventos de sucesso (`events.vehicle.reserved`, `events.vehicle.released`) ou falha (`events.vehicle.reservation_failed`).

*   **`pagamento-service`**:
    *   **Responsabilidade**: Gera códigos de pagamento únicos para transações específicas e processa pagamentos.
    *   **Tecnologias**: FastAPI, SQLAlchemy (PostgreSQL).
    *   **Endpoints Expostos**: `/payment-codes`, `/payments`, `/health`.
    *   **Comunicação (Pub/Sub)**: Responde a comandos de geração de código (`commands.payment.generate_code`), processamento (`commands.payment.process`) e reembolso (`commands.payment.refund`) de pagamentos. Publica eventos de sucesso (`events.payment.code_generated`, `events.payment.processed`, `events.payment.refunded`) ou falha (`events.payment.code_generation_failed`, `events.payment.failed`, `events.payment.refund_failed`).

*   **`orquestrador`**:
    *   **Responsabilidade**: Atua como o coordenador da Saga de compra de veículos. Recebe a requisição inicial de compra, emite comandos aos outros microsserviços e reage aos eventos para avançar no fluxo da transação ou iniciar a lógica de compensação em caso de falha. Mantém o estado da transação Saga.
    *   **Tecnologias**: FastAPI, SQLAlchemy (PostgreSQL), `httpx` (para comunicação síncrona com `veiculo-service` ao marcar veículo como vendido), Google Cloud Pub/Sub.
    *   **Endpoints Expostos**: `/purchase` (inicia a Saga), `/saga-states/{transaction_id}` (consulta o estado da Saga), `/health`.
    *   **Comunicação (Pub/Sub)**: Envia comandos e escuta todos os eventos relevantes dos outros microsserviços para orquestrar o fluxo.

### Tecnologias e Justificativas

*   **Python com FastAPI**:
    *   **Justificativa**: Escolha para desenvolvimento rápido de APIs web com alta performance, validação de dados automática (Pydantic) e geração de documentação OpenAPI/Swagger.

*   **PostgreSQL (com SQLAlchemy ORM)**:
    *   **Justificativa**: Banco de dados relacional robusto e amplamente utilizado. SQLAlchemy provê um ORM flexível para interação com o banco de dados. A abordagem é "Database per Service" (embora no ambiente local os serviços compartilhem uma instância PostgreSQL, cada um tem seu próprio schema/tabelas e modelos de dados isolados).

*   **Google Cloud Pub/Sub**:
    *   **Justificativa**: Serviço de mensagens assíncronas totalmente gerenciado na GCP. Ideal para comunicação entre microsserviços, permitindo desacoplamento, resiliência e suporte a padrões de Event-Driven Architecture (EDA) e Sagas. O emulador local facilita o desenvolvimento e testes sem depender da nuvem.

*   **Pydantic (Modelos Compartilhados)**:
    *   **Justificativa**: Usado para definir a estrutura de Commands e Events de forma clara e tipada em `shared/models.py`. Garante consistência nos payloads de mensagem entre os serviços.

*   **Docker e Docker Compose**:
    *   **Justificativa**: Essenciais para containerização dos microsserviços, garantindo ambientes de execução consistentes. Docker Compose facilita a orquestração e execução de todo o ambiente local de desenvolvimento, incluindo banco de dados e emulador de Pub/Sub.

*   **Terraform**:
    *   **Justificativa**: Ferramenta de Infrastructure as Code (IaC) para provisionar e gerenciar recursos na Google Cloud Platform (GCP). Permite a criação de ambientes repetíveis, versionamento da infraestrutura e automação do deploy.

*   **Google Cloud Run (futuro deploy)**:
    *   **Justificativa (prévia)**: Um serviço de computação serverless e totalmente gerenciado para containers, ideal para microsserviços baseados em HTTP. Permite escalabilidade automática e pagamento por uso.

*   **Google Cloud SQL (futuro deploy)**:
    *   **Justificativa (prévia)**: Um serviço de banco de dados relacional totalmente gerenciado na GCP, suportando PostgreSQL. Simplifica a operação e escalabilidade do banco de dados.

*   **Google Secret Manager (futuro deploy)**:
    *   **Justificativa (prévia)**: Serviço gerenciado para armazenar credenciais e segredos de forma segura, permitindo que os serviços do Cloud Run acessem senhas de banco de dados sem tê-las hardcoded.

*   **Google Artifact Registry (futuro deploy)**:
    *   **Justificativa (prévia)**: Repositório de artefatos gerenciado (incluindo imagens Docker) na GCP, para armazenar e gerenciar as imagens dos microsserviços antes do deploy no Cloud Run.

*   **Pytest (com httpx e asyncio)**:
    *   **Justificativa**: Framework de testes robusto e flexível para Python, com suporte assíncrono para testar APIs e fluxos de integração complexos de forma eficiente.

### Padrão Saga (Orquestrador)

O processo de compra de um veículo é uma transação distribuída, o que significa que envolve múltiplos serviços e potencialmente falhas em diferentes etapas. Para garantir a consistência dos dados, é implementado o padrão Saga, especificamente o modelo de **Orquestrador**.

O serviço `orquestrador` é o responsável por:
1.  **Iniciar a transação**: Recebe a requisição de compra e salva um estado inicial.
2.  **Emitir comandos**: Envia mensagens para os serviços participantes (crédito, veículo, pagamento) instruindo-os a realizar suas partes da transação.
3.  **Monitorar eventos**: Escuta os eventos de sucesso ou falha publicados pelos serviços participantes.
4.  **Controlar o fluxo**: Decide o próximo passo (avançar ou compensar) com base nos eventos recebidos.
5.  **Compensar falhas**: Se uma etapa falhar, o orquestrador coordena as ações de compensação para reverter as alterações feitas por etapas anteriores, garantindo a consistência do sistema.

**Exemplo do Fluxo de Saga de Compra (Atualmente Implementado):**

1.  **Início da Compra**: O `orquestrador` recebe um `PurchaseRequest`.
2.  **Reserva de Crédito**: O `orquestrador` envia um `ReserveCreditCommand` para o `cliente-service`.
    *   Se `CreditReservedEvent` for recebido: Prossegue para a próxima etapa.
    *   Se `CreditReservationFailedEvent` for recebido: A Saga falha, e o orquestrador marca o estado como `FAILED`.
3.  **Reserva de Veículo**: O `orquestrador` envia um `ReserveVehicleCommand` para o `veiculo-service`.
    *   Se `VehicleReservedEvent` for recebido: Prossegue para a próxima etapa.
    *   Se `VehicleReservationFailedEvent` for recebido: A Saga falha, e o `orquestrador` inicia a compensação, enviando um `ReleaseCreditCommand` de volta para o `cliente-service`.
4.  **Geração de Código de Pagamento**: O `orquestrador` envia um `GeneratePaymentCodeCommand` para o `pagamento-service`.
    *   Se `PaymentCodeGeneratedEvent` for recebido: Prossegue para a próxima etapa.
    *   Se `PaymentCodeGenerationFailedEvent` for recebido: A Saga falha, e o `orquestrador` inicia a compensação, enviando um `ReleaseVehicleCommand` e, posteriormente, um `ReleaseCreditCommand`.
5.  **Processamento de Pagamento**: O `orquestrador` envia um `ProcessPaymentCommand` para o `pagamento-service`.
    *   Se `PaymentProcessedEvent` for recebido: Prossegue para a próxima etapa.
    *   Se `PaymentFailedEvent` for recebido: A Saga falha, e o `orquestrador` inicia a compensação, enviando um `ReleaseVehicleCommand` e, posteriormente, um `ReleaseCreditCommand`.
6.  **Marcar Veículo como Vendido**: Após o pagamento ser processado, o `orquestrador` faz uma chamada HTTP direta para o `veiculo-service` (`PATCH /vehicles/{vehicle_id}/mark_as_sold`) para finalizar a transação.
7.  **Saga Completa**: Se todas as etapas forem bem-sucedidas, o `orquestrador` marca o estado da Saga como `COMPLETED`.

## Estado Atual da Aplicação

Atualmente, o projeto possui a estrutura base de microsserviços e a Saga de compra implementada.

### Funcionalidades Existentes:

*   **Microsserviços `cliente-service`, `veiculo-service`, `pagamento-service`, `orquestrador`**: APIs básicas para cadastro, consulta e controle de estado.
*   **Comunicação Assíncrona**: Utilização de Google Cloud Pub/Sub para troca de comandos e eventos entre os serviços.
*   **Fluxo de Saga de Compra**: O `orquestrador` coordena a reserva de crédito, reserva de veículo, geração de código de pagamento e processamento de pagamento. A lógica de compensação para falhas nessas etapas está presente.
*   **Persistência**: Cada serviço utiliza seu próprio esquema no PostgreSQL para armazenar dados.
*   **Containerização**: Todos os serviços são conteinerizados com Dockerfiles.
*   **Ambiente Local**: Um `docker-compose.yml` completo permite iniciar todos os serviços (incluindo PostgreSQL e Pub/Sub Emulator) para desenvolvimento e testes locais.
*   **Infraestrutura como Código**: Módulos Terraform estão definidos para provisionar instâncias de Cloud SQL, Cloud Run Services, Artifact Registry e Secret Manager no GCP.
*   **Scripts de Automação**: `Makefile` e scripts auxiliares para `setup`, `deploy`, `destroy` e gerenciamento do ambiente de desenvolvimento.
*   **Testes**: Uma suíte de testes em Pytest que inclui testes de unidade, integração (fluxo completo de compra, cenários de falha) e performance básica.

### Funcionalidades Pendentes (Próximas Etapas):

*   **`cliente-service`**:
    *   **Modelagem de Dados**: Complementar os campos de dados sensíveis para clientes conforme as necessidades de negócio (documentação, pagamento).
    *   **APIs de Edição**: Implementar endpoints para edição de dados de clientes.
    *   **Listagens**: Implementar listagens de veículos à venda e vendidos, com ordenação por preço.

*   **`veiculo-service`**:
    *   **Modelagem de Dados**: Complementar os campos de dados sensíveis para veículos conforme as necessidades de negócio (documentação, pagamento).
    *   **APIs de Edição**: Implementar endpoints para edição de dados de veículos.
    *   **Listagens**: Implementar listagens de veículos à venda e vendidos, com ordenação por preço.

*   **Processo de Venda**:
    *   Refinar a modelagem do processo de "seleção do veículo pelo cliente, até a baixa do veículo no estoque", incluindo os detalhes para "receber o código de pagamento, pagar pelo veículo e retirá-lo".
    *   Mapear e implementar os tratamentos para "problemas podem ocorrer no caminho: entre o processo do(a) cliente selecionar o veículo e realizar a reserva, outro(a) cliente reserva o veículo antes, ou o pagamento não é efetuado, ou o cliente desiste da compra em qualquer um dos passos." (alguns já são tratados pela Saga, outros podem exigir lógica adicional).

*   **Segurança de Dados Sensíveis**:
    *   Definir e implementar regras de segurança para dados sensíveis e o processo de tratamento (políticas de acesso, criptografia, mascaramento de dados em APIs/logs, etc.).

*   **Documentação Final**:
    *   Desenho da arquitetura a ser utilizada no projeto (com justificação e segurança de serviços na nuvem).
    *   Relatório de segurança de dados.
    *   Relatório técnico sobre o tipo de orquestração SAGA.

## Como Executar Localmente

### Pré-requisitos

*   Docker e Docker Compose instalados.
*   Python 3.11+ (para execução direta de scripts, embora os serviços rodem em containers).

### Passos

1.  **Construir as imagens dos serviços**:
    ```bash
    make build
    ```
2.  **Iniciar os serviços**:
    ```bash
    make up
    ```
    Ou, para o modo de desenvolvimento com logs em tempo real:
    ```bash
    make dev
    ```
    Os serviços estarão disponíveis em:
    *   Cliente: `http://localhost:8080`
    *   Veículo: `http://localhost:8081`
    *   Pagamento: `http://localhost:8082`
    *   Orquestrador: `http://localhost:8083`
    *   Pub/Sub Emulator: `localhost:8085`
    *   PostgreSQL: `localhost:5432`

3.  **Executar os testes (opcional)**:
    Com os serviços rodando (via `make up` ou `make dev` em outro terminal):
    ```bash
    make test
    ```
    Ou, se quiser pular o `docker-compose up`:
    ```bash
    make test-fast
    ```

4.  **Parar os serviços**:
    ```bash
    make stop
    ```
5.  **Limpar recursos locais (volumes, redes, etc.)**:
    ```bash
    make clean
    ```

## Deploy na Google Cloud Platform (GCP)

O deploy na GCP é gerenciado via Terraform e scripts auxiliares.

### Pré-requisitos para Deploy na GCP

*   Conta GCP com um projeto configurado.
*   `gcloud CLI` instalado e autenticado.
*   `terraform` instalado.

### Passos para Deploy

1.  **Configurar o projeto GCP e credenciais**:
    ```bash
    make setup
    ```
    Você será solicitado a informar o `PROJECT_ID` e definir uma senha para o banco de dados.

2.  **Configurar o backend remoto do Terraform (Google Cloud Storage)**:
    ```bash
    make setup-backend
    ```
    Isso criará um bucket GCS para armazenar o estado do Terraform de forma segura.

3.  **Realizar o deploy inicial da infraestrutura e dos serviços**:
    ```bash
    make deploy
    ```
    Este comando irá:
    *   Habilitar APIs necessárias no GCP.
    *   Aplicar a configuração Terraform (Cloud SQL, Artifact Registry, Secret Manager, Cloud Run Services com imagens placeholder).
    *   Construir e enviar as imagens Docker dos seus microsserviços para o Artifact Registry.
    *   Atualizar os serviços do Cloud Run para usar suas imagens reais.

    Ao final, os URLs dos serviços implantados no Cloud Run serão exibidos.

### Comandos de Gerenciamento da Infraestrutura

*   **Deploy apenas do SQL**: `make deploy-sql`
*   **Deploy apenas dos códigos dos serviços (após alterações no código)**: `make deploy-code`
*   **Destruir toda a infraestrutura (CUIDADO!)**: `make destroy`
*   **Destruir apenas o SQL**: `make destroy-sql`
*   **Destruir apenas os serviços (aplicações)**: `make destroy-app`

---