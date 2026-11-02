;:;
;:;
;:; Bu lispler Elk-Elktronik Mühendisi Cagdas Yildirim tarafindan hazirlandi
;:; e-mail: sjjscagdas@hotmail.com
;:; Cagdas Muhendislik Osmaniye
;:;
;:;
-------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------
--------------------------------------------------------------------------------------------
(defun c:jjj (/ SS1 E# ENT NAMES LYR)
  (setq olderr *error*
*error* ff_hata
  )
  (setvar "cmdecho" 0)
  (setq SS1 (ssget)
E#  (sslength SS1)
  )
  (if (> E# 0)
    (progn
      (setq ENT   (ssname SS1
  (setq E# (1- E#))

  )
    ENT   (entget ENT)
    NAMES (cdr (assoc 8 ENT))
    E#   (1- E#)
      )
    )
  )
  (while (> E# -1)
    (setq ENT (ssname SS1 E#)
  ENT (entget ENT)
  LYR (cdr (assoc 8 ENT))
  NAMES (strcat NAMES "," LYR)
  E# (1- E#)
    )
  )
  (command "LAYER" "F" NAMES "")
  (princ)
)