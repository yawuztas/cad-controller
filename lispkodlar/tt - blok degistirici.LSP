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
(DEFUN C:TT ()
(IF (= TTYPE NIL)(SETQ TTYPE "TAP4"))
(PRINC "degistirilecek blogun adý<")(PRINC TTYPE)(PRINC "> ")
(SETQ TTYPE1 (GETSTRING))
(IF (/= TTYPE1 "" )(SETQ TTYPE TTYPE1))
(INITGET 1)
(SETVAR "OSMODE" 0)(SETVAR "PICKBOX" 3)
(PRINC "eski blogu secin > ")
(SETQ AA (SSGET))
(SETQ J (1- (SSLENGTH AA)))
(WHILE (>= J 0)
(SETQ ID (SSNAME AA J))
(SETQ BIL (ENTGET ID))
(SETQ INS (CDR (ASSOC 10 BIL)))
(SETQ ANG (CDR (ASSOC 50 BIL)))
(SETQ ANG (/ (* 180 ANG) PI))
(SETQ INS (CDR (ASSOC 10 BIL)))
(SETQ LAY (CDR (ASSOC 8 BIL)))
(ENTDEL ID)
(COMMAND "INSERT" TTYPE INS "" "" ANG)
(COMMAND "CHPROP" "L" "" "LA" LAY "")
(SETQ J (1- J))
(COMMAND "OSMODE" "695")
)
)