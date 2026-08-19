((python-mode
  ;; Activar direnv (esto sí)
  (eval . (direnv-update-environment))

  ;; Python shell
  (python-shell-virtualenv-root . ".venv")

  ;; Pyright: NO forzar venv aquí
  ;; Pyright: NO tocar workspace folders
  ;; Pyright: NO limitar clientes
))
