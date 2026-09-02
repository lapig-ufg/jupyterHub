# Como integrar o health-check ao stack

## 1. Build da imagem

```bash
cd health-check/
docker build -t lapig/jupyterhub-monitor:v1 .
```

## 2. Adicionar ao docker-compose.yml do stack (jupyterhub-sci2)

Adiciona o serviço `monitor` dentro do `docker-compose.yml` que já tem o `jupyterhub` e o `glances`:

```yaml
services:

  # ... seus serviços existentes (jupyterhub, glances) ...

  monitor:
    image: lapig/jupyterhub-monitor:v1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro   # acesso somente-leitura ao socket
      - /home/lapig/applications/service/jupyterHub/logs:/logs  # onde os logs serão salvos
    environment:
      - MONITOR_INTERVAL=60        # intervalo de coleta em segundos
      - MEM_WARN_PERCENT=90        # % de RAM para gerar WARNING
      - LOGS_BASE=/logs
    networks:
      - web_lapig_sci2
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      restart_policy:
        condition: on-failure
```

## 3. Criar a pasta de logs no host antes de subir

```bash
mkdir -p /home/lapig/applications/service/jupyterHub/logs/jupyterhub
mkdir -p /home/lapig/applications/service/jupyterHub/logs/users
```

## 4. Redeployar o stack

```bash
cd docker/
docker stack deploy -c docker-compose.yml jupyterhub-sci2
```

## 5. Verificar que está rodando

```bash
docker service ls | grep monitor
docker service logs jupyterhub-sci2_monitor -f
```

---

## Estrutura de logs gerada automaticamente

```
logs/
├── jupyterhub/
│   ├── health.log    # linhas [I] do Hub (spawns, logins, etc.)
│   └── error.log     # linhas [W][E][C] do Hub
└── users/
    ├── aurilio/
    │   ├── health.log    # saúde periódica (CPU, RAM, uptime)
    │   └── error.log     # OOM, crashes, alta memória
    ├── tiago/
    │   ├── health.log
    │   └── error.log
    └── ...             # criado automaticamente para cada usuário
```

---

## Variáveis de ambiente disponíveis

| Variável          | Default | Descrição                                    |
|-------------------|---------|----------------------------------------------|
| `MONITOR_INTERVAL`| `60`    | Intervalo entre coletas (segundos)            |
| `MEM_WARN_PERCENT`| `90`    | % de RAM para gerar WARNING no error.log      |
| `LOGS_BASE`       | `/logs` | Pasta base dos logs dentro do container       |

---

## Exemplos de log gerado

### logs/users/aurilio/health.log
```
2026-09-02 19:30:00 | aurilio | RUNNING | CPU: 2.3% | RAM: 1.20G/2.00G (60.0%) | UPTIME: 2h 5m 10s | PIDS: 12
2026-09-02 19:31:00 | aurilio | RUNNING | CPU: 1.8% | RAM: 1.21G/2.00G (60.5%) | UPTIME: 2h 6m 10s | PIDS: 12
```

### logs/users/aurilio/error.log — OOM
```
2026-09-02 20:00:00 | SEVERITY: CRITICAL | USER: aurilio | CONTAINER: jupyter-aurilio
  EVENT    : OOM_KILLED
  REASON   : Container excedeu o limite de memória (mem_limit: 2.00G)
  MEM_USAGE: 2.00G / 2.00G (100.0%)
  CPU_USAGE: 45.2%
  UPTIME   : 3h 22m 0s
  PID_COUNT: 47
  EXIT_CODE: 137
  RESTARTED: False
  ACTION   : Container morto pelo kernel — OOM Killer ativado
  ----------------------------------------
```

### logs/users/aurilio/error.log — WARNING
```
2026-09-02 19:50:00 | SEVERITY: WARNING | USER: aurilio | CONTAINER: jupyter-aurilio
  EVENT    : HIGH_MEMORY
  MEM_USAGE: 1.85G / 2.00G (92.5%)
  CPU_USAGE: 78.1%
  THRESHOLD: 90.0% do limite
  UPTIME   : 3h 12m 0s
  ACTION   : Aviso — container próximo do limite de memória
  ----------------------------------------
```