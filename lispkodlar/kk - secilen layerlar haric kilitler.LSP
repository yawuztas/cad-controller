;:;
;:;
;:; Bu lispler Elk-Elktronik Mühendisi Cagdas Yildirim tarafindan hazirlandi
;:; e-mail: sjjscagdas@hotmail.com
;:; Cagdas Muhendislik Osmaniye
;:;
;:;
-------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------
(defun c:kk (/ lc_sec lc_kat lc_katman)
  (setq lc_sec (ssget))
  (if (= lc_sec nil)
    (progn
    )
    (progn
      (setq lc_say (sslength lc_sec)
    lc_c   0
      )
      (setq lc_katman (cdr (assoc 8 (entget (ssname lc_sec lc_c)))))
      (setq lc_c 1)
      (while (< lc_c lc_say)
(setq lc_tek (ssname lc_sec lc_c))
(setq lc_kat (cdr (assoc 8 (entget lc_tek))))
(setq lc_katman (strcat lc_katman "," lc_kat))
(setq lc_c (+ lc_c 1))
      )
      (command "layer" "lock" "*" "")
      (command "layer" "unlock" lc_katman "")
    )
  )
  (princ)
)