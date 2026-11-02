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
(DEFUN C:DD (/ SS E)
   (SETQ SS(SSGET))
   (IF SS (PROGN
            (COMMAND "CHANGE" SS "" "PROP" "LAYER" (GETVAR "CLAYER") "")
   )))