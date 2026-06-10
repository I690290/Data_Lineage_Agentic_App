      *================================================================
      * PROGRAM  : CRXMLGEN
      * SYSTEM   : Credit Risk Behaviour Scoring System
      * MODULE   : MI4014 Daily Transaction Extract - Phase 4 XML
      * PURPOSE  : Read the DFSORT-merged extract file and generate
      *            XML output file matching the Oracle external table
      *            structure for BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES
      *            _DIARIAS.
      *
      * INPUT    : BHSCOMRG - MERGED.BHSCORE.EXTRACT (FB/LRECL=160)
      *                       produced by DFSORT STEP030
      * OUTPUT   : BHSCOXML - MI4014_Transaction_Extract_TSB_NAM65_
      *                       YYYYMMDD.xml (VB)
      *
      * CALLED BY: JCL CRJBHSCR STEP040
      * CALLS    : None
      *
      * XML OUTPUT FORMAT per Oracle External Table DDL:
      *   RECORDS DELIMITED BY </Item>
      *   Each record wrapped in <Item>...</Item>
      *   Fields enclosed by XML tags matching Oracle ENCLOSED BY
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRXMLGEN.
       AUTHOR. CREDIT-RISK-BATCH.
       DATE-WRITTEN. 2024-03-15.
       DATE-COMPILED.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MERGED-INPUT-FILE
               ASSIGN TO BHSCOMRG
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-INPUT-STATUS.

           SELECT XML-OUTPUT-FILE
               ASSIGN TO BHSCOXML
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-XML-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  MERGED-INPUT-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 160 CHARACTERS.
       COPY CRTRANSR.

       FD  XML-OUTPUT-FILE
           RECORDING MODE V
           RECORD CONTAINS 1 TO 32000 CHARACTERS.
       01  XML-OUTPUT-RECORD           PIC X(32000).

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-INPUT-STATUS     PIC XX   VALUE SPACES.
           05  WS-XML-STATUS       PIC XX   VALUE SPACES.

       01  WS-COUNTERS.
           05  WS-RECS-READ        PIC 9(9) VALUE ZEROS.
           05  WS-RECS-WRITTEN     PIC 9(9) VALUE ZEROS.

       01  WS-FLAGS.
           05  WS-INPUT-EOF        PIC X    VALUE 'N'.
               88  INPUT-EOF-REACHED VALUE 'Y'.

       01  WS-RETURN-CODE          PIC S9(4) COMP VALUE ZEROS.
       01  WS-OUTPUT-DATE          PIC X(8).
       01  WS-XML-LINE             PIC X(2000).
       01  WS-XML-LINE-LEN         PIC S9(4) COMP VALUE ZEROS.

      *    Amount in display format with sign and 2 decimal places
       01  WS-AMT-DISPLAY          PIC -9(13).99.
       01  WS-AMT-TRIMMED          PIC X(20).
       01  WS-AMT-PTR              PIC 9(3).

      *    XML tag copybook
       COPY CRXMLTAG.

       PROCEDURE DIVISION.
      *================================================================
       MAIN-PARA.
           PERFORM INIT-PARA.
           PERFORM WRITE-XML-HEADER-PARA.
           PERFORM READ-LOOP-PARA UNTIL INPUT-EOF-REACHED.
           PERFORM WRITE-XML-FOOTER-PARA.
           PERFORM CLOSE-FILES-PARA.
           PERFORM DISPLAY-TOTALS-PARA.
           MOVE WS-RETURN-CODE TO RETURN-CODE.
           STOP RUN.

      *================================================================
       INIT-PARA.
           MOVE ZEROS TO WS-COUNTERS.
           MOVE 'N'   TO WS-INPUT-EOF.
           MOVE FUNCTION CURRENT-DATE(1:8) TO WS-OUTPUT-DATE.

           OPEN INPUT  MERGED-INPUT-FILE.
           IF WS-INPUT-STATUS NOT = '00'
               DISPLAY 'CRXMLGEN: OPEN ERROR BHSCOMRG STATUS='
                       WS-INPUT-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.

           OPEN OUTPUT XML-OUTPUT-FILE.
           IF WS-XML-STATUS NOT = '00'
               DISPLAY 'CRXMLGEN: OPEN ERROR BHSCOXML STATUS='
                       WS-XML-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.

           DISPLAY 'CRXMLGEN: XML GENERATION STARTED. DATE='
                   WS-OUTPUT-DATE.

      *================================================================
       WRITE-XML-HEADER-PARA.
      *    Write XML root element and file metadata header
           MOVE '<?xml version="1.0" encoding="UTF-8"?>' TO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.
           MOVE '<MI4014_TRANSACTION_EXTRACT>' TO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.
           STRING '  <FileDate>' WS-OUTPUT-DATE '</FileDate>'
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.
           MOVE '  <Source>TSB_NAM65</Source>' TO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *================================================================
       READ-LOOP-PARA.
           READ MERGED-INPUT-FILE
               AT END MOVE 'Y' TO WS-INPUT-EOF
           END-READ.

           IF INPUT-EOF-REACHED
               NEXT SENTENCE
           ELSE
               ADD 1 TO WS-RECS-READ
               PERFORM WRITE-XML-ITEM-PARA
           END-IF.

      *================================================================
       WRITE-XML-ITEM-PARA.
      *    Build one XML <Item>...</Item> block per input record
      *    Field order and tag names match Oracle External Table DDL:
      *    external_account_number, sub_no, book_id, transaction_code,
      *    transaction_amt, tran_category, posted_date, effective_date,
      *    unsec_ind, New_Main_Account_Number, New_Loan_Account_Number

      *    Opening <Item> tag
           MOVE CXMT-ITEM-OPEN TO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    external_account_number -> Oracle MAIN_ACCOUNT_NUMBER
           STRING '  ' CXMT-EXT-ACCT-OPEN
                  FUNCTION TRIM(CTR-EXTERNAL-ACCT-NUM)
                  CXMT-EXT-ACCT-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    sub_no -> Oracle SUB_ACCOUNT_NUMBER
           STRING '  ' CXMT-SUB-NO-OPEN
                  FUNCTION TRIM(CTR-SUB-ACCOUNT-NUM)
                  CXMT-SUB-NO-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    book_id -> Oracle COMPANY
           STRING '  ' CXMT-BOOK-ID-OPEN
                  FUNCTION TRIM(CTR-BOOK-ID)
                  CXMT-BOOK-ID-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    transaction_code -> Oracle TRANSACTION_CODE
           STRING '  ' CXMT-TRAN-CODE-OPEN
                  FUNCTION TRIM(CTR-TRANSACTION-CODE)
                  CXMT-TRAN-CODE-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    transaction_amt -> Oracle TRANSACTION_AMOUNT
           MOVE CTR-TRANSACTION-AMT TO WS-AMT-DISPLAY.
           STRING '  ' CXMT-TRAN-AMT-OPEN
                  FUNCTION TRIM(WS-AMT-DISPLAY)
                  CXMT-TRAN-AMT-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    tran_category -> Oracle TRANSACTION_GROUP
           STRING '  ' CXMT-TRAN-CAT-OPEN
                  FUNCTION TRIM(CTR-TRAN-CATEGORY)
                  CXMT-TRAN-CAT-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    posted_date -> Oracle POSTED_DATE
           STRING '  ' CXMT-POSTED-DT-OPEN
                  FUNCTION TRIM(CTR-POSTED-DATE)
                  CXMT-POSTED-DT-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    effective_date -> Oracle EFFECTIVE_DATE
           STRING '  ' CXMT-EFFEC-DT-OPEN
                  FUNCTION TRIM(CTR-EFFECTIVE-DATE)
                  CXMT-EFFEC-DT-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    unsec_ind -> Oracle UNSECURED
           STRING '  ' CXMT-UNSEC-OPEN
                  CTR-UNSECURED-IND
                  CXMT-UNSEC-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    New_Main_Account_Number -> Oracle NEW_MAIN_ACC_NUM
           STRING '  ' CXMT-NEW-MAIN-OPEN
                  FUNCTION TRIM(CTR-NEW-MAIN-ACCT-NUM)
                  CXMT-NEW-MAIN-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    New_Loan_Account_Number -> Oracle NEW_LOAN_ACC_NUM
           STRING '  ' CXMT-NEW-LOAN-OPEN
                  FUNCTION TRIM(CTR-NEW-LOAN-ACCT-NUM)
                  CXMT-NEW-LOAN-CLOSE
               DELIMITED SIZE INTO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *    Closing </Item> delimiter — Oracle RECORDS DELIMITED BY
           MOVE CXMT-ITEM-CLOSE TO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

           ADD 1 TO WS-RECS-WRITTEN.

      *================================================================
       WRITE-XML-FOOTER-PARA.
           MOVE '</MI4014_TRANSACTION_EXTRACT>' TO WS-XML-LINE.
           PERFORM WRITE-XML-LINE-PARA.

      *================================================================
       WRITE-XML-LINE-PARA.
           MOVE FUNCTION LENGTH(FUNCTION TRIM(WS-XML-LINE))
               TO WS-XML-LINE-LEN.
           MOVE FUNCTION TRIM(WS-XML-LINE) TO XML-OUTPUT-RECORD.
           WRITE XML-OUTPUT-RECORD.
           IF WS-XML-STATUS NOT = '00'
               DISPLAY 'CRXMLGEN: WRITE ERROR STATUS=' WS-XML-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.
           MOVE SPACES TO WS-XML-LINE.

      *================================================================
       CLOSE-FILES-PARA.
           CLOSE MERGED-INPUT-FILE.
           CLOSE XML-OUTPUT-FILE.

      *================================================================
       DISPLAY-TOTALS-PARA.
           DISPLAY '**CRXMLGEN TOTALS**'.
           DISPLAY '  INPUT  DATASET  : MERGED.BHSCORE.EXTRACT'.
           DISPLAY '  OUTPUT XML FILE : MI4014_Transaction_Extract'
                   '_TSB_NAM65_' WS-OUTPUT-DATE '.xml'.
           DISPLAY '  RECORDS READ    : ' WS-RECS-READ.
           DISPLAY '  RECORDS WRITTEN : ' WS-RECS-WRITTEN.
           DISPLAY '  RETURN CODE     : ' WS-RETURN-CODE.
