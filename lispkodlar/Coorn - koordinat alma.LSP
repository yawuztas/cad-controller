;;;;-------------------------------------------------------------------------------
;;;; Program Name: ECoor.lsp [Extraction Coordinates]
;;;; Created By:   Vladimir Azarko (VVA) (Email: azarko@yandex.ru)
;;;; Posted http://www.cadtutor.net/forum/showthread.php?t=31653
;;;; Date Created: I do not remember when the beginnings
;;;; Function:     Export coordinates with some options
;;; Commands:
;;;           COORa  - export coordinates
;;;           COORN - export coordinates with numbering
;;;                   Numbers of points are drawn by the text on the current layer,
;;;                   the current style, current height (TEXTSIZE)
;;;           COORNP - CoorNP-Coordinates + Numbers + Points. Draw points with current value of PDMODE and PDSIZE 
;;;           COORT - export of coordinates with numbering where number considers the text nearest to a point
;;;;-------------------------------------------------------------------------------
;;;; Revision History
;;;; Rev  By     Date    Description
;;;;-------------------------------------------------------------------------------
;;;; 1    VVA   9-02-09  Has started to put things in order

(vl-load-com)

;;; =============== COMMAND SECTION START ==================

(defun c:COOR ( / ptLst)
  (vl-load-com)
  (if (setq ptLst (vva-get-final-points-list))
    (vva-export-point ptLst nil nil)
    )
  (princ)
  )
;|=============== Команда COORN ===============================================

EN:
   Export of coordinates of the specified points, the chosen objects: points, blocks, polylines, splines in a text file, Excel With numbers.
   Text file — txt, or csv. A rounding off of coordinates according to current adjustments of a command _UNITS (LUPREC !!!)
   And make P
RUS:
Экспорт координат указанных точек, выбранных объектов: точек, блоков, полилиний, сплайнов в текстовый файл, ексел с простановкой номеров
Текстовый файл — либо txt, либо csv.
Номера точек отрисовываются текстом на текущем слое, текущим стилем, текущей высотой
Округление координат в соответствии с текущими настройками команды _UNITS (переменная LUPREC !!!)

|;

(defun c:COORN ( / ptLst)
  (vl-load-com)
  (if (setq ptLst (vva-get-final-points-list))
    (vva-export-point ptLst t nil)
    )
  (princ)
  )
(defun c:COORNP ( / ptLst)
  (vl-load-com)
  (if (setq ptLst (vva-get-final-points-list))
    (vva-export-point ptLst t t)
    )
  (princ)
  )
(defun c:COORT( /  ptLst objSet lw buf pat isRus oFlag sFlag txtList filPath cFile)
    (vl-load-com)
(setq isRus (= (getvar "SysCodePage") "ANSI_1251"))
(if (setq ptLst (vva-get-final-points-list))
  (progn
    (setq objSet(ssget "_X" (list '(0 . "*TEXT")(cons 410 (getvar "CTAB")))))
    (setq lw (vl-remove-if 'listp(mapcar 'cadr(ssnamex objSet))))
    (setq lw (mapcar '(lambda(x)(setq x (entget x))(list (cdr(assoc 10 x))(cdr(assoc 1 x)))) lw))
    (foreach pt ptlst
      (setq pt (trans pt 1 0))
      (setq buf (mapcar '(lambda(x)(list (distance pt (car x))(cadr x))) lw))
      (setq pat (car buf))
      (foreach dst buf (if (< (car dst) (car pat))(setq pat dst)))
      (setq txtList (cons (cadr pat) txtList))
      )
    (setq txtList (reverse txtList))
    (princ "\n+++++++ Coordinates list +++++++\n")
    (setq buf
    (mapcar '(lambda (x y)
               (princ (strcat "\n" y "  "
                              (rtos (car x))
                              ","
                              (rtos (cadr x))
                              (if (= 3 (length x))
                                (strcat "," (rtos (nth 2 x)))
                                ""
                              ) ;_ end of if
                      ) ;_ end of strcat
               ) ;_ end of princ
              (list y (rtos (car x))(rtos (cadr x))
                              (if (= 3 (length x))(rtos (nth 2 x))) ;_ end of if
                      )
             ) ;_ end of lambda
            ptLst txtList
    );_ end mapcar
          )
    (princ "\n\n+++++++++ End of list +++++++++")
  (initget
    "Файл Excel Не Text Excel Not _Text Excel Not Text Excel Not"
  ) ;_ end of initget
  (setq sFlag
         (getkword
           (if IsRus
             "\nСохранить координаты в [Файл txt или csv/Excel/Не сохранять] <Файл> : "
             "\nSave coordinates to [Txt or csv file/Excel/Not save] <Text> : "
           ) ;_ end of if
         ) ;_ end of getkword
  ) ;_ end of setq
    (if (null sFlag)
      (setq sFlag "Text")
    ) ;_ end of if
    (cond ((and (= "Text" sFlag)
              (setq filPath
                     (getfiled (if IsRus
                                 "Сохранение координат в текстовый или csv файл"
                                 "Save Coordinates to Text or CSV File"
                               ) ;_ end of if
                               "Coordinates.csv"
                               "csv;txt"
                               17
                     ) ;_ end of getfiled
              ) ;_ end of setq
         ) ;_ end of and
         (if (= (strcase (vl-filename-extension filPath)) ".CSV")
           (setq pat ";")
           (setq pat "      ")
         ) ;_ end of if
         (if (or (not (findfile filPath))
                 (and  (findfile filPath)
                       (VL-FILE-SYSTIME filPath)
                       )
                 )
           (progn
         (setq cFile (open filPath "w"))
         (foreach ln buf
             (write-line
               (apply 'strcat
               (append (list(car ln))
                       (mapcar '(lambda(x)(strcat "," x))
                               (cdr ln)
                               )
                       )
                 )     
               cFile
             ) ;_ end of write-line
           )
         (close cFile)
         (initget "Yes No")
         (setq oFlag (getkword (if IsRus
                                 "\nОткрыть файл? [Yes/No] <No> : "
                                 "\nOpen text file? [Yes/No] <No> : "
                               ) ;_ end of if
                     ) ;_ end of getkword
         ) ;_ end of setq
         (if (= oFlag "Yes")
           ;;; (startapp "notepad.exe" filPath)
           (vva-xopen filPath)
         ) ;_ end of if
         )
           (alert (strcat (if IsRus "Невозможно открыть " "Do not open") "\n" filPath))
           )
        )
                                               ; end condition #1
          ((= "Excel" sFlag)
           (xls buf
                (if IsRus
                  '("Номер точки" "X" "Y" "Z")
                  '("Number" "X" "Y" "Z")
                  )
                nil
                "COORT"
           ) ;_ end of xls
          )                                       ; end condition #2
          (t nil)
    ) ;_ end of cond
  ) ;_ end of progn
) ;_ end of if
 (princ))

;;; =============== COMMAND SECTION END ==================

;;; ==================== Helper function Start ===========================
;|================== XLS ========================================
*  published http://www.autocad.ru/cgi-bin/f1/board.cgi?t=31371zf
               http://forum.dwg.ru/showthread.php?t=20509
* Purpose: Export of the list of data Data-list in Excell
*             It is exported to a new leaf of the current book.
              If the book is not present, it is created
* Arguments:
              Data-list — The list of lists of data (LIST)
                            ((Value1 Value2 ... VlalueN)(Value1 Value2 ... VlalueN)...)
                            Each list of a kind (Value1 Value2... VlalueN) enters the name in
                            a separate line in corresponding columns (Value1-A Value2-B and .т.д.)
                  header —  The list (LIST) headings or nil a kind (" Signature A " " Signature B "...)
                            If header nil, is accepted ("X" "Y" "Z")
                 Colhide —  The list of alphabetic names of columns to hide or nil — to not hide ("A" "C" "D") — to hide columns A, C, D
                 Name_list — The name of a new leaf of the active book or nil — is not present
* Return: nil
* Usage
(xls '((1.1 1.2 1.3 1.4)(2.1 2.2 2.3 2.4)(3.1 3.2 3.3 3.4)) '("Col1" "Col2" "Col3"  "Col4") '("B") "test")   |;


;|================== XLS ========================================
* Опубликовано http://www.autocad.ru/cgi-bin/f1/board.cgi?t=19833nl&page=2
               http://forum.dwg.ru/showthread.php?t=20509
               http://www.autocad.ru/cgi-bin/f1/board.cgi?t=31596eW
* Автор: Владимир Азарко aka VVA
* Назначение: Печать списка данных Data-list в Excell
*             Для вывода создается новая книга
              Вывод осуществляется в первом листе
* Аргументы:
              Data-list — список списков данных (LIST) вида
                            ((Value1 Value2 ... VlalueN)(Value1 Value2 ... VlalueN)...)
                            Каждый список вида (Value1 Value2 ... VlalueN) записывается
                            в отдельную строку в соответствующие столбцы (Value1-A Value2-B и .т.д.)
                  header —  список (LIST) заголовков или nil вида ("Подпись A" "Подпись B" ...)
                            Если header nil, принимается ("X" "Y" "Z")
                 Colhide —  список буквенных названий стоблцов для скрытия или nil — не скрывать
                            ("A" "C" "D") — скрыть столбцы A, C, D
                 Name_list — имя нового листа активной книги или nil — новая книга
* Возврат: nil
* TIPS!!! : При передачи функции xls числовых вещественных данных нет необходимости проверять текущий системный
            разделитель целой и дробной части ("HKEY_CURRENT_USER\\Control Panel\\International" "sDecimal")
            Функцией на время вывода отключается использование в Excele системного разделителя, разделителем
            целой и дробной части устанавливается точка. После завершения ф-ции все восстанавливается.
Пример вызова
(xls '((1.1 1.2 1.3 1.4)(2.1 2.2 2.3 2.4)(3.1 3.2 3.3 3.4)) '("Столбец1" "Столбец2" "Столбец3" "Столбец4") '("B"))|;
(vl-load-com)
(defun xls ( Data-list header Colhide Name_list / *aplexcel* *books-colection* Currsep
*excell-cells* *new-book* *sheet#1* *sheet-collection* col iz_listo row cell cols)
(defun Letter (N / Res TMP)(setq Res "")(while (> N 0)(setq TMP (rem N 26)
  TMP (if (zerop TMP)(setq N (1- N) TMP 26) TMP)
  Res (strcat (chr (+ 64 TMP)) Res)  N   (/ N 26))) Res)
(if (null Name_list)(setq Name_list ""))
  (setq  *AplExcel*     (vlax-get-or-create-object "Excel.Application"))
  (if (setq *New-Book*  (vlax-get-property *AplExcel* "ActiveWorkbook"))
    (setq *Books-Colection*  (vlax-get-property *AplExcel* "Workbooks")
          *Sheet-Collection* (vlax-get-property *New-Book* "Sheets")
               *Sheet#1*     (vlax-invoke-method *Sheet-Collection* "Add"))
(setq *Books-Colection*  (vlax-get-property *AplExcel* "Workbooks")
              *New-Book*     (vlax-invoke-method *Books-Colection* "Add")
          *Sheet-Collection* (vlax-get-property *New-Book* "Sheets")
               *Sheet#1*     (vlax-get-property *Sheet-Collection* "Item" 1)))
(setq *excell-cells*     (vlax-get-property *Sheet#1* "Cells"))
(setq Name_list (if (= Name_list "")
                  (vl-filename-base(getvar "DWGNAME"))
                  (strcat (vl-filename-base(getvar "DWGNAME")) "&" Name_list))
   col 0 cols nil)
(if (> (strlen Name_list) 26)
(setq Name_list (strcat (substr Name_list 1 10) "..." (substr Name_list (- (strlen Name_list) 13) 14))))
(vlax-for sh *Sheet-Collection* (setq cols (cons (strcase(vlax-get-property sh 'Name)) cols)))
(setq row Name_list)
(while (member (strcase row) cols)(setq row (strcat Name_list " (" (itoa(setq col (1+ col)))")")))
(setq Name_list row)
(vlax-put-property *Sheet#1* 'Name Name_list)
(setq Currsep (vlax-get-property *AplExcel* "UseSystemSeparators"))
(vlax-put-property *AplExcel* "UseSystemSeparators" :vlax-false) ;_не использовать системные установки
(vlax-put-property *AplExcel* "DecimalSeparator" ".")            ;_разделитель дробной и целой части
(vlax-put-property *AplExcel* "ThousandsSeparator" " ")          ;_разделитель тысячей
(vla-put-visible *AplExcel* :vlax-true)(setq row 1 col 1)
(if (null header)(setq header '("X" "Y" "Z")))
(repeat (length header)(vlax-put-property *excell-cells* "Item" row col
(vl-princ-to-string (nth (1- col) header)))(setq col (1+ col)))(setq  row 2 col 1)
(repeat (length Data-list)(setq iz_listo (car Data-list))(repeat (length iz_listo)
(vlax-put-property *excell-cells* "Item" row col (vl-princ-to-string (car iz_listo)))
(setq iz_listo (cdr iz_listo) col (1+ col)))(setq Data-list (cdr Data-list))(setq col 1 row (1+ row)))
(setq col (1+(length header)) row (1+ row))
(setq cell (vlax-variant-value (vlax-invoke-method *Sheet#1* "Evaluate"
    (strcat "A1:" (letter col)(itoa row))))) ;_ end of setq
(setq cols (vlax-get-property cell  'Columns))
(vlax-invoke-method cols 'Autofit)
(vlax-release-object cols)(vlax-release-object cell)
(foreach item ColHide (if (numberp item)(setq item (letter item)))
(setq cell (vlax-variant-value (vlax-invoke-method *Sheet#1* "Evaluate"
    (strcat item "1:" item "1"))))
(setq cols (vlax-get-property cell  'Columns))
(vlax-put-property cols 'hidden 1)
(vlax-release-object cols)(vlax-release-object cell))
(vlax-put-property *AplExcel* "UseSystemSeparators" Currsep)
(mapcar 'vlax-release-object (list *excell-cells* *Sheet#1* *Sheet-Collection* *New-Book* *Books-Colection*
*AplExcel*))(setq *AplExcel* nil)(gc)(gc)(princ))
(defun group-by-num (lst num / ls ret)(if (= (rem (length lst) num ) 0)(progn (setq ls nil)
  (repeat (/ (length lst) num)(repeat num (setq ls(cons (car lst) ls)lst (cdr lst)))
  (setq ret (append ret (list (reverse ls))) ls nil)))) ret)
(defun PtCollect(SelSet)(mapcar 'cdr (mapcar '(lambda(x)(assoc 10 x))(mapcar 'entget
(vl-remove-if 'listp(mapcar 'cadr(ssnamex SelSet))))))); end of PtCollect
(defun PLCollect(SelSet / ret)
(foreach lw (mapcar 'vlax-ename->vla-object (vl-remove-if 'listp(mapcar 'cadr(ssnamex SelSet))))
  (cond ((wcmatch (vla-get-ObjectName lw) "*Polyline")
  (setq ret (append ret (group-by-num (vlax-get lw 'Coordinates)
  (if (=(vla-get-ObjectName lw) "AcDbPolyline") 2 3)))))
       ((=(vla-get-ObjectName lw) "AcDbSpline")(setq ret (append ret (group-by-num
         (vlax-safearray->list(vlax-variant-value (vla-get-controlpoints lw)))  3))))
      (t nil))) ret)
;;;Отрисовка текста
;;; txt - текст
;;; pnt - точка отрисовки в ПСК
;;; heigtht - высота
;;; rotation - угол поворота
;;;justification - или nil
;;;Возвращает имя примитива
(defun vva-text-draw (txt pnt height rotation justification)
   (if (null pnt)(command "_.-TEXT" "" txt)
   (if (= (cdr (assoc 40 (tblsearch "STYLE" (getvar "TEXTSTYLE"))))
    0.0
       ) ;_ end of =
     (progn
     ;; нулевая высота текста
       (if justification
   (command "_.-TEXT" "_J" justification "_none" pnt height rotation txt)
   (command "_.-TEXT" "_none" pnt height rotation txt)
       ) ;_ end of if
     ) ;_ end of progn
     (progn
       ;; фиксированнная высота
       (if justification
   (command "_.-TEXT" "_J" justification "_none" pnt rotation txt)
   (command "_.-TEXT" "_none" pnt rotation txt)
       ) ;_ end of if
     ) ;_ end of progn
   ) ;_ end of if
     )
  (entlast)
)
(defun vva-get-final-points-list ( / isRus  curPt ptLst objSet  )
  (setq isRus(= (getvar "SysCodePage") "ANSI_1251"))
  (if(not ptcol:mode)(setq ptcol:mode "Pick"))
  (initget "Указать Точка Блоки Полилиния Pick pOints Blocks poLyline _Pick pOints Blocks poLyline Pick pOints Blocks poLyline")
(setq oldMode ptcol:mode ptcol:mode
(getkword (if IsRus (strcat "\nВыберите режим [Указать/Точка/Блоки/Полилиния или сплайн] <"
(cadr (assoc ptcol:mode '(("Pick" "Указать")("pOints" "Указать")("Blocks" "Блоки")("poLyline" "Полилиния")))) ">: ")
        (strcat "\nSpecify mode [Pick/pOints/Blocks/poLyline or spline] <"ptcol:mode">: "))) ptLst nil)
(if(null ptcol:mode)(setq ptcol:mode oldMode))
(cond ((= "Pick" ptcol:mode)(setq curPt T)
       (while curPt (setq curPt(getpoint (if IsRus
         "\nУкажите точку или Enter завершения > " "\nPick point or Enter to continue > ")))
  (if curPt (setq ptLst(append ptLst(list (trans curPt 1 0))))))); end condition #1
      ((= "pOints" ptcol:mode)(if (not(setq objSet(ssget "_I" '((0 . "POINT")))))(progn
         (if IsRus (princ "\nВыберите точки и нажмите Enter ")(princ "\nSelect points and press Enter "))
   (setq objSet(ssget '((0 . "POINT"))))))(if objSet (setq ptLst(PtCollect objSet)))); end condition #2
      ((= "Blocks" ptcol:mode)(if (not(setq objSet(ssget "_I" '((0 . "INSERT")))))(progn
        (if IsRus(princ "\nВыберите блоки и нажмите Enter ")(princ "\nSelect blocks and press Enter "))
     (setq objSet(ssget '((0 . "INSERT"))))))(if objSet (setq ptLst(PtCollect objSet)))); end condition #3
      ((= "poLyline" ptcol:mode)(if (not(setq objSet(ssget "_I" '((0 . "*POLYLINE,SPLINE")))))(progn
        (if IsRus(princ "\nВыберите полилинии и нажмите Enter  ")(princ "\nSelect polyline and press Enter "))
     (setq objSet(ssget '((0 . "*POLYLINE,SPLINE"))))))(if objSet (setq ptLst(PLCollect objSet)))); end condition #4
); end cond
(if ptLst (progn (princ "\n+++++++ Coordinates list +++++++\n")(setq ptLst (mapcar '(lambda(x)(trans x 0 1)) ptLst))
(mapcar '(lambda(x)(princ(strcat "\n"(rtos(car x))","(rtos(cadr x))
(if(= 3(length x))(strcat ","(rtos(nth 2 x))) "")))) ptLst); end mapcar
(princ "\n\n+++++++++ End of list +++++++++")
            )
  )
 ptLst
  )
(defun vva-xopen (name / di na sh) 
;; http://www.theswamp.org/index.php?topic=29548.0 
;;;Usage 
;;;(setq my_file (vva-xopen "c:/test.txt")) 
;;;(setq my_file (vva-xopen "c:/test.avi")) 
;;;(setq my_file (vva-xopen "c:/test.3gp")) 

  (and   (setq name (findfile name)) 
   (setq sh (vlax-create-object "Shell.Application")) 
   (setq di (vlax-invoke sh 'Namespace (vl-filename-directory name))) 
   (setq na (vlax-invoke di 'parsename (strcat (vl-filename-base name) (vl-filename-extension name)))) 
   (vlax-invoke-method na 'invokeverbex "open") 
  ) 
  (vlax-release-object sh) 
  na 
)

(defun vva-export-point (ptlst isNum isPoint / Npt IsRus sFlag oFlag Step pat)
  ;;; ptLst - points list
  ;;; isNum - t - numerate nil -not
  ;;; isPoint - t - create point nil - not
  (setq isRus (= (getvar "SysCodePage") "ANSI_1251"))
  (if isNum
  (setq Npt (getint (if IsRus
                      "\nНачальный номер точки <Не маркировать> : "
                      "\nStart number of points <Don't mark> : "
                    ) ;_ end of if
            ) ;_ end of getint
  ) ;_ end of setq
    )
  (setq Step 1)
  (if (numberp Npt)
    (progn
      (princ (if IsRus
               "\nПриращение числа"
               "\nIncrement of number"
             ) ;_ end of if
      ) ;_ end of princ
      (if (not (numberp ptcol:Step))
        (setq ptcol:Step 1)
      ) ;_ end of if
      (princ " <")
      (princ ptcol:Step)
      (princ ">: ")
      (setq Step (getint))
      (if (null Step)
        (setq Step ptcol:Step)
      ) ;_ end of if
      (setq ptcol:Step Step)
    ) ;_ end of progn
  ) ;_ end of if
  (initget
    "Файл Excel Не Text Excel Not _Text Excel Not Text Excel Not"
  ) ;_ end of initget
  (setq sFlag
         (getkword
           (if IsRus
             "\nСохранить координаты в [Файл txt или csv/Excel/Не сохранять] <Файл> : "
             "\nSave coordinates to [Txt or csv file/Excel/Not save] <Text> : "
           ) ;_ end of if
         ) ;_ end of getkword
  ) ;_ end of setq
  (if (null sFlag)
    (setq sFlag "Text")
  ) ;_ end of if
  (setq oFlag Npt)
  (if (numberp Npt)
    (foreach ln ptlst
      (vva-text-draw ;_Отрисовка текста
        (itoa Npt) ;_Номер точки
        (polar ln (/ pi 4) 0.15) ;_Координаты на 1 ед по углом 45 градусов
        (getvar "TEXTSIZE") ;_ Текущей высотой текста
        0 ;_Угол поворота
        nil
      ) ;_ end of vva-text-draw
      (if isPoint (entmakex (list (cons 0 "POINT") (cons 10 (trans ln 1 0)))))
      ;;_Make POINT
      (setq Npt (+ Npt Step))
    ) ;_ end of foreach
  ) ;_ end of if
  (setq Npt oFlag)
  (setq ptLst (mapcar '(lambda (x) (mapcar 'rtos x)) ptlst))
  (cond ((and (= "Text" sFlag)
              (setq filPath
                     (getfiled (if IsRus
                                 "Сохранение координат в текстовый или csv файл"
                                 "Save Coordinates to Text or CSV File"
                               ) ;_ end of if
                               "Coordinates.csv"
                               "csv;txt"
                               1
                     ) ;_ end of getfiled
              ) ;_ end of setq
         ) ;_ end of and
         (if (= (strcase (vl-filename-extension filPath)) ".CSV")
           (setq pat ";")
           (setq pat "      ")
         ) ;_ end of if
         (if (or (not (findfile filPath))
                 (and  (findfile filPath)
                       (VL-FILE-SYSTIME filPath)
                       )
                 )
           (progn
         (setq cFile (open filPath "w"))
         (foreach ln ptLst
           (write-line
             (strcat (if (numberp Npt)
                       (strcat (itoa Npt) pat)
                       ""
                     ) ;_ end of if
                     (car ln)
                     pat
                     (cadr ln)
                     (if (= 3 (length ln))
                       (strcat pat (nth 2 ln))
                     ) ;_ end of if
             ) ;_ end of strcat
             cFile
           ) ;_ end of write-line
           (if (numberp Npt)
             (setq Npt (+ Npt Step))
           ) ;_ end of if
         ) ;_ end of foreach
         (close cFile)
         (initget "Yes No")
         (setq oFlag (getkword (if IsRus
                                 "\nОткрыть файл? [Yes/No] <No> : "
                                 "\nOpen text file? [Yes/No] <No> : "
                               ) ;_ end of if
                     ) ;_ end of getkword
         ) ;_ end of setq
         (if (= oFlag "Yes")
           ;;; (startapp "notepad.exe" filPath)
           (vva-xopen filPath)
         ) ;_ end of if
         )
           (alert (strcat (if IsRus "Невозможно открыть " "Do not open") "\n" filPath))
           )
        )                                         ; end condition #1
        ((= "Excel" sFlag)
         (if (numberp Npt)
           (progn
             (setq Npt (- Npt Step))
             (setq ptlst
                    (mapcar '(lambda (x) (cons (setq Npt (+ Npt Step)) x))
                            ptlst
                    ) ;_ end of mapcar
             ) ;_ end of setq
             (xls ptlst '("N" "X" "Y" "Z") nil "COORN")
           ) ;_ end of progn
           (xls ptLst nil nil "COOR")
         ) ;_ end of if
        )                                         ; end condition #2
        (t nil)
  ) ;_ end of cond
  (princ)
) ;_ end of defun

;;; ==================== Helper function End   ===========================

(princ "\nFor use type Coor, CoorN, CoorNP or CoorT in command line ")
(princ)
