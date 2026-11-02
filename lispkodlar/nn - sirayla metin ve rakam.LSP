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
(defun c:nn ()
(setq tc_met (getstring t "\nSayýlarýn baþýna gelecek metni yazýn:"))
  (if (= tc_met nil)
    (progn)
    (progn
 
  (setq tc_num (getint "\nBirinci Numara:"))
  (if (= tc_num nil)
    (progn)
    (progn
      (setvar "errno" 0)
      (setq tc_num_uy tc_num)
      (setq tc_ent nil)
      (while (= tc_ent nil)
(initget "C")
(setq tc_ent (entsel "\nYazýyý Seç / Cýkýþ:"))
(if (= tc_ent nil)
  (progn
    (if (= (getvar "errno") 0)
      (progn
(setq tc_ent nil)
(setvar "errno" 0)
      )
    )
    (if (= (getvar "errno") 52)
      (progn
(setq tc_ent t)
(setvar "errno" 0)
      )
    )
  )
  (progn
    (setq tc_tan (cdr (assoc 0 (entget (car tc_ent)))))
    (if (/= tc_tan "TEXT")
      (progn
(princ "\nSeçilen nesne yazý deðil...")
(setq tc_ent nil)
      )
      (progn
(setq tc_stil (cdr (assoc 7 (entget (car tc_ent)))))
(setq tc_stil_yuk
       (cdr (assoc 40 (tblsearch "style" tc_stil))
       )
)
(if (= tc_stil_yuk 0.0)
  (progn
    (command "change" tc_ent "" "" "" "" "" "" (strcat tc_met (rtos tc_num_uy 2 0)))
    (setq tc_num_uy (1+ tc_num_uy))
    (setq tc_ent nil)
  )
  (progn
    (command "change" tc_ent "" ""
     ""       ""       "" (strcat tc_met (rtos tc_num_uy 2 0)
    ))
    (setq tc_num_uy (1+ tc_num_uy))
    (setq tc_ent nil)
  )
)
      )
    )
  )
)
      )
    )
  )))
  (princ)
)
(princ)