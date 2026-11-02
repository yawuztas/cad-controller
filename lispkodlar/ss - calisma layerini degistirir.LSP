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
(defun c:ss (/ e n)
        (setq e (car (entsel " Kullanmak istediginiz layeri tiklayin : ")))
        (if e (progn
                (setq e (entget e))
                (setq n (cdr (assoc 8 e)))
                (command "layer" "set" n "")
        ))
)