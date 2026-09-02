#!/usr/bin/env python3
"""
LAPIG JupyterHub — Container Health Monitor
Monitora containers de usuário (jupyter-*) a cada 1 minuto.
Registra saúde periódica e erros (OOM, crashes, alta memória).
"""

import docker
import time
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────
# Configuração
# ──────────────────────────────────────────

LOGS_BASE        = Path(os.environ.get("LOGS_BASE", "/logs"))
INTERVAL_SECONDS = int(os.environ.get("MONITOR_INTERVAL", 60))
MEM_WARN_PERCENT = float(os.environ.get("MEM_WARN_PERCENT", 90.0))  # % para gerar WARNING

HUB_LOG_DIR   = LOGS_BASE / "jupyterhub"
USERS_LOG_DIR = LOGS_BASE / "users"


# ──────────────────────────────────────────
# Helpers de logging
# ──────────────────────────────────────────

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def get_logger(log_path: Path, name: str) -> logging.Logger:
    """Retorna um logger de arquivo dedicado."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(fh)
    return logger


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def uptime_str(started_at: str) -> str:
    """Converte o campo StartedAt do Docker em string legível."""
    try:
        # Docker retorna ISO 8601 com nanosegundos — remove nanosegundos
        ts = started_at[:26] + "Z"
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        return f"{h}h {m}m {s}s"
    except Exception:
        return "N/A"


# ──────────────────────────────────────────
# Funções de log por usuário
# ──────────────────────────────────────────

def user_from_container(name: str) -> str:
    """Extrai o username do nome do container (jupyter-<username>)."""
    return name.removeprefix("jupyter-").removeprefix("/jupyter-")


def get_user_loggers(username: str):
    user_dir = USERS_LOG_DIR / username
    ensure_dir(user_dir)
    health = get_logger(user_dir / "health.log", f"{username}.health")
    error  = get_logger(user_dir / "error.log",  f"{username}.error")
    return health, error


def parse_mem(stats: dict) -> tuple[float, float, float]:
    """
    Retorna (usage_gb, limit_gb, percent).
    Usa memory_stats do docker stats.
    """
    mem = stats.get("memory_stats", {})
    usage = mem.get("usage", 0) - mem.get("stats", {}).get("cache", 0)
    limit = mem.get("limit", 1)
    usage_gb = usage / (1024 ** 3)
    limit_gb = limit / (1024 ** 3)
    percent  = (usage / limit * 100) if limit > 0 else 0
    return usage_gb, limit_gb, percent


def parse_cpu(stats: dict) -> float:
    """Retorna uso de CPU em %."""
    try:
        cpu  = stats["cpu_stats"]
        pcpu = stats["precpu_stats"]
        delta   = cpu["cpu_usage"]["total_usage"] - pcpu["cpu_usage"]["total_usage"]
        sys_del = cpu.get("system_cpu_usage", 0) - pcpu.get("system_cpu_usage", 0)
        ncpus   = cpu.get("online_cpus", len(cpu["cpu_usage"].get("percpu_usage", [1])))
        if sys_del > 0:
            return (delta / sys_del) * ncpus * 100.0
    except (KeyError, ZeroDivisionError):
        pass
    return 0.0


def log_health(username: str, container_name: str, stats: dict, inspect: dict):
    health_log, _ = get_user_loggers(username)
    mem_u, mem_l, mem_pct = parse_mem(stats)
    cpu = parse_cpu(stats)
    uptime = uptime_str(inspect["State"].get("StartedAt", ""))
    pid_count = inspect["State"].get("Pid", 0)

    health_log.info(
        f"{now()} | {username} | RUNNING"
        f" | CPU: {cpu:.1f}%"
        f" | RAM: {mem_u:.2f}G/{mem_l:.2f}G ({mem_pct:.1f}%)"
        f" | UPTIME: {uptime}"
        f" | PIDS: {pid_count}"
    )

    # Gera WARNING se memória acima do threshold
    if mem_pct >= MEM_WARN_PERCENT:
        _, error_log = get_user_loggers(username)
        separator = "-" * 40
        error_log.warning(
            f"\n{now()} | SEVERITY: WARNING | USER: {username} | CONTAINER: {container_name}\n"
            f"  EVENT    : HIGH_MEMORY\n"
            f"  MEM_USAGE: {mem_u:.2f}G / {mem_l:.2f}G ({mem_pct:.1f}%)\n"
            f"  CPU_USAGE: {cpu:.1f}%\n"
            f"  THRESHOLD: {MEM_WARN_PERCENT}% do limite\n"
            f"  UPTIME   : {uptime}\n"
            f"  ACTION   : Aviso — container próximo do limite de memória\n"
            f"  {separator}"
        )


def log_oom(username: str, container_name: str, inspect: dict, stats: dict):
    _, error_log = get_user_loggers(username)
    mem_u, mem_l, mem_pct = parse_mem(stats)
    cpu = parse_cpu(stats)
    uptime = uptime_str(inspect["State"].get("StartedAt", ""))
    pid_count = inspect["State"].get("Pid", 0)
    exit_code = inspect["State"].get("ExitCode", "?")
    restarted = inspect["State"].get("Restarting", False)
    separator = "-" * 40

    error_log.error(
        f"\n{now()} | SEVERITY: CRITICAL | USER: {username} | CONTAINER: {container_name}\n"
        f"  EVENT    : OOM_KILLED\n"
        f"  REASON   : Container excedeu o limite de memória (mem_limit: {mem_l:.2f}G)\n"
        f"  MEM_USAGE: {mem_u:.2f}G / {mem_l:.2f}G ({mem_pct:.1f}%)\n"
        f"  CPU_USAGE: {cpu:.1f}%\n"
        f"  UPTIME   : {uptime}\n"
        f"  PID_COUNT: {pid_count}\n"
        f"  EXIT_CODE: {exit_code}\n"
        f"  RESTARTED: {restarted}\n"
        f"  ACTION   : Container morto pelo kernel — OOM Killer ativado\n"
        f"  {separator}"
    )


def log_exit_error(username: str, container_name: str, inspect: dict,
                   stats: dict, last_logs: str):
    _, error_log = get_user_loggers(username)
    mem_u, mem_l, mem_pct = parse_mem(stats)
    cpu = parse_cpu(stats)
    uptime = uptime_str(inspect["State"].get("StartedAt", ""))
    exit_code = inspect["State"].get("ExitCode", "?")
    separator = "-" * 40

    error_log.error(
        f"\n{now()} | SEVERITY: ERROR | USER: {username} | CONTAINER: {container_name}\n"
        f"  EVENT    : CONTAINER_EXITED\n"
        f"  EXIT_CODE: {exit_code}\n"
        f"  REASON   : Saída anormal (código diferente de 0)\n"
        f"  MEM_USAGE: {mem_u:.2f}G / {mem_l:.2f}G ({mem_pct:.1f}%)\n"
        f"  CPU_USAGE: {cpu:.1f}%\n"
        f"  UPTIME   : {uptime}\n"
        f"  LAST_LOGS:\n{last_logs}\n"
        f"  {separator}"
    )


# ──────────────────────────────────────────
# Logger do próprio Hub (stdout → arquivos)
# ──────────────────────────────────────────

def setup_hub_loggers():
    ensure_dir(HUB_LOG_DIR)
    hub_health = get_logger(HUB_LOG_DIR / "health.log", "hub.health")
    hub_error  = get_logger(HUB_LOG_DIR / "error.log",  "hub.error")
    return hub_health, hub_error


def collect_hub_logs(client: docker.DockerClient, hub_health, hub_error):
    """Lê os últimos logs do container do JupyterHub e separa por nível."""
    try:
        hub_containers = client.containers.list(
            filters={"name": "jupyterhub-sci2_jupyterhub"}
        )
        if not hub_containers:
            return
        container = hub_containers[0]
        raw_logs = container.logs(tail=50, timestamps=True).decode("utf-8", errors="replace")

        for line in raw_logs.splitlines():
            if not line.strip():
                continue
            # Níveis do JupyterHub: [I]=info, [W]=warning, [E]=error, [C]=critical
            if " [I " in line:
                hub_health.info(line)
            elif any(level in line for level in (" [W ", " [E ", " [C ")):
                hub_error.warning(line)
    except Exception as e:
        hub_error.error(f"{now()} | MONITOR_ERROR | Falha ao coletar logs do Hub: {e}")


# ──────────────────────────────────────────
# Loop principal
# ──────────────────────────────────────────

def monitor_once(client: docker.DockerClient, hub_health, hub_error,
                 seen_oom: set, seen_exit: set):
    """Uma rodada de monitoramento — chamada a cada INTERVAL_SECONDS."""

    # 1. Logs do Hub
    collect_hub_logs(client, hub_health, hub_error)

    # 2. Containers de usuário ativos (jupyter-*)
    try:
        user_containers = client.containers.list(filters={"name": "jupyter-"})
    except Exception as e:
        hub_error.error(f"{now()} | MONITOR_ERROR | Falha ao listar containers: {e}")
        return

    for container in user_containers:
        name = container.name
        username = user_from_container(name)

        try:
            inspect = client.api.inspect_container(name)
            state   = inspect.get("State", {})

            # Pula containers sem atividade real (sem PID ou parados)
            if not state.get("Running") and not state.get("OOMKilled"):
                continue

            # Coleta stats (bloqueia brevemente por 1 ciclo de CPU)
            stats = container.stats(stream=False)

            # ── OOM ──
            if state.get("OOMKilled") and name not in seen_oom:
                log_oom(username, name, inspect, stats)
                seen_oom.add(name)

            # ── Exit code anormal (não OOM, não 0) ──
            elif not state.get("Running") and state.get("ExitCode", 0) not in (0, 137):
                if name not in seen_exit:
                    last_logs = container.logs(tail=5).decode("utf-8", errors="replace")
                    last_logs = "\n".join(
                        f"    {l}" for l in last_logs.splitlines()
                    )
                    log_exit_error(username, name, inspect, stats, last_logs)
                    seen_exit.add(name)

            # ── Saúde periódica (container running) ──
            elif state.get("Running"):
                # Limpa do seen se voltou a rodar
                seen_oom.discard(name)
                seen_exit.discard(name)
                log_health(username, name, stats, inspect)

        except Exception as e:
            _, error_log = get_user_loggers(username)
            error_log.error(
                f"{now()} | SEVERITY: ERROR | USER: {username} | CONTAINER: {name}\n"
                f"  EVENT  : MONITOR_COLLECTION_ERROR\n"
                f"  DETAIL : {e}\n"
                f"  {'-'*40}"
            )


def main():
    print(f"[{now()}] LAPIG Health Monitor iniciando — intervalo: {INTERVAL_SECONDS}s")

    ensure_dir(HUB_LOG_DIR)
    ensure_dir(USERS_LOG_DIR)

    client = docker.from_env()
    hub_health, hub_error = setup_hub_loggers()

    # Conjuntos pra evitar logar o mesmo evento OOM/exit várias vezes
    seen_oom:  set = set()
    seen_exit: set = set()

    hub_health.info(f"{now()} | MONITOR_START | Health Monitor iniciado")

    while True:
        try:
            monitor_once(client, hub_health, hub_error, seen_oom, seen_exit)
        except Exception as e:
            hub_error.error(f"{now()} | MONITOR_CRASH | Erro inesperado no loop: {e}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()