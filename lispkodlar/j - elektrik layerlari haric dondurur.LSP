;:;
;:;
;:; Bu lispler Elk-Elktronik Mühendisi Cagdas Yildirim tarafindan hazirlandi
;:; e-mail: sjjscagdas@hotmail.com
;:; Cagdas Muhendislik Osmaniye
;:;
;:;
-------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------
(defun c:j () 
 (setq ec_lay_list "00-03,00-04,00-05,00-06,00-07,00-24V,00-ACIL_AYD,00-ANHTR,00-AYD,00-CCTV,00-CERCEVE,00-DATA,00-ELKYAZ,00-GÜV,00-INTERCOM,
00-KANAL_DOSEME,00-KANAL_KUVVET,00-KANAL_ZAYIF,00-KOL_NO,00-KORNA,00-LINYE_NO,
00-OTOPARK,00-PRZ,00-SES,00-TABLO,00-TEL,00-TOPRAK,00-TV,00-UPS,00-YANGIN,00-YANGIN_KONV,00-YAZI")
   (command "layer" "freeze" "*" "")
   (command "layer" "thaw" ec_lay_list "")
  (princ))
