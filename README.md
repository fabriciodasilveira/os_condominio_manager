# Condomínio OS PWA (FastAPI)

Aplicação PWA para gestão de ordens de serviço de condomínio com backend em Python FastAPI.

## Funcionalidades implementadas

- Autenticação com perfis: `administrador`, `morador`, `sindico`, `funcionario`
- Estrutura multi-condomínio:
  - `associação` (condomínio principal)
  - `subconjunto` (subcondomínio/setor)
  - `moradia` com chave composta por subconjunto + número
  - georreferência da moradia: `latitude` e `longitude`
  - carga automática de coordenadas a partir de `app/endecos.py` (formato `condominioX-unidade`)
- Painel de administrador para:
  - cadastrar subconjuntos
  - cadastrar síndico e associar ao subconjunto
  - cadastrar moradores já vinculados ao subconjunto/moradia
  - pesquisar moradores por nome, usuário ou número de moradia
  - resetar senha de moradores
- Criação de OS com:
  - categoria (`eletrica`, `hidraulica`, `limpeza`, `pintura`, `seguranca`, `outros`)
  - prioridade (`baixa`, `media`, `alta`, `urgente`)
  - upload de foto
- Dashboard Kanban com colunas:
  - `backlog`, `fazendo`, `pendentes`, `concluido`
- Filtros e busca textual
- Notificações internas por usuário
- Mapa de OS abertas para síndico/administrador com pontos georreferenciados
- Relatórios com:
  - total de OS
  - distribuição por status/categoria/prioridade
  - tempo médio de resolução
- Push Notification Web (estilo app de entrega) para morador em mudança de status
- PWA com `manifest.json` e `service worker`

## Stack

- Backend: FastAPI + SQLAlchemy + PostgreSQL + JWT
- Frontend: HTML/CSS/JS puro (PWA)
- Push: `pywebpush` (VAPID)

## Como rodar

1. Criar ambiente virtual e instalar dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Criar `.env` baseado em `.env.example`:

```bash
cp .env.example .env
```

3. Subir API:

```bash
uvicorn app.main:app --reload --port 8182
```

4. Abrir no navegador:

- [http://localhost:8182](http://localhost:8182)

## Banco PostgreSQL

O projeto agora usa PostgreSQL por padrão. Configure via `.env`:

- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_EXTERNAL_PORT` (porta exposta para acessar de fora, ex.: DBeaver)

Opcionalmente, você pode definir `DATABASE_URL` diretamente.

Exemplo para evitar conflito com `5432` já ocupada:

- `DB_EXTERNAL_PORT=5433` (ou `5434`)

## Deploy com Docker Compose

1. Criar `.env`:

```bash
cp .env.example .env
```

2. Subir serviços (API + PostgreSQL):

```bash
docker compose up -d --build
```

3. Acessar aplicação:

- [http://localhost:8182](http://localhost:8182)

4. Acesso externo ao PostgreSQL (cliente SQL):

- host: `localhost` (ou IP do servidor)
- porta: valor de `DB_EXTERNAL_PORT` (padrão `5433`)
- banco: `DB_NAME`
- usuário: `DB_USER`
- senha: `DB_PASSWORD`

### Modo desenvolvimento com reload

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Usuários demo criados automaticamente

- `admin1` / `123456`
- `morador1` / `123456`
- `sindico1` / `123456`
- `funcionario1` / `123456`

## Push notifications (VAPID)

Para ativar push real, preencha no `.env`:

- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_CLAIMS_SUB`

Sem essas chaves, o sistema continua funcionando com notificações internas no dashboard.

## Endpoints principais

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/admin/subsets`
- `POST /api/admin/subsets`
- `POST /api/admin/managers`
- `GET /api/admin/residents`
- `POST /api/admin/residents`
- `PATCH /api/admin/residents/{id}/reset-password`
- `GET /api/map/open-work-orders`
- `POST /api/work-orders`
- `GET /api/work-orders`
- `PATCH /api/work-orders/{id}/status`
- `PATCH /api/work-orders/{id}/assign`
- `GET /api/notifications`
- `POST /api/push/subscribe`
- `GET /api/reports/summary`
