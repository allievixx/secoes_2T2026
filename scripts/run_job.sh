#!/bin/sh
set -eu
echo "BOOT: iniciando job; preparando Xvfb e Python; wrapper_pid=$$" >&2
if [ "$$" -eq 1 ]; then
	echo "BOOT ERROR: wrapper como PID 1; use o entrypoint com tini para evitar bloqueio do xvfb-run" >&2
	exit 1
fi
exec xvfb-run -a -e /dev/stderr python -u -c '
import faulthandler
import runpy
import sys
print("BOOT: Xvfb iniciado; Python ativo; importando pipeline", flush=True)
faulthandler.enable()
sys.argv = ["scripts.gerar_dados", *sys.argv[1:]]
runpy.run_module("scripts.gerar_dados", run_name="__main__")
' "$@"