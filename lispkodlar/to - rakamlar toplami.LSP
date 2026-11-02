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
(defun c:to ()
(setq e (car (entsel " toplanacak rakamlara tiklayin : ")))
 (setq objs (ssget))
 (setq tot_obj (sslength objs)
       last_obj 0
       total 0)
 (while (< last_obj tot_obj)
   (if 
          (= "TEXT" (cdr (assoc 0 (setq ent (entget (ssname objs last_obj))))))
          (progn                               ;do§ruysa yap
            (setq s_temp (cdr (assoc 1 ent)))
            (setq val (atoi s_temp))
            (setq total (+ total val))
            (setq last_obj (1+ last_obj))      
          )
          (setq last_obj (1+ last_obj))
   )
 )
 (setvar "cmdecho" 1)  
 (alert (strcat "\nrakamlar toplami= " (itoa total)))
 (princ)
)