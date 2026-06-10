      *================================================================
      * PROGRAM  : CRDB2EXT
      * SYSTEM   : Credit Risk Behaviour Scoring System
      * MODULE   : MI4014 Daily Transaction Extract - Phase 1
      * PURPOSE  : Extract customer account data from DB2 table
      *            CRISK.CUST_ACCOUNT_MASTER for all accounts
      *            eligible for behaviour scoring.
      *            Output: Sequential flat file for CRTXNEXT input.
      *
      * INPUT    : DB2 table CRISK.CUST_ACCOUNT_MASTER
      *            (cursor-driven, no input file)
      * OUTPUT   : CUST.BHSCORE.EXTRACT (FB/LRECL=140)
      *
      * CALLED BY: JCL CRJBHSCR STEP010
      * CALLS    : None
      *
      * DB2 TABLES ACCESSED:
      *   READ   : CRISK.CUST_ACCOUNT_MASTER
      *
      * RETURN CODES:
      *   0000 = Successful completion
      *   0008 = DB2 error encountered
      *   0012 = File I/O error
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRDB2EXT.
       AUTHOR. CREDIT-RISK-BATCH.
       DATE-WRITTEN. 2024-03-15.
       DATE-COMPILED.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT EXTRACT-FILE
               ASSIGN TO BHSCOEXT
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-EXTRACT-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  EXTRACT-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 140 CHARACTERS.
       COPY CRCUSTAC.

       WORKING-STORAGE SECTION.
      *----------------------------------------------------------------
      * File status and counters
      *----------------------------------------------------------------
       01  WS-FILE-STATUS.
           05  WS-EXTRACT-STATUS   PIC XX   VALUE SPACES.

       01  WS-COUNTERS.
           05  WS-ROWS-FETCHED     PIC 9(9) VALUE ZEROS.
           05  WS-ROWS-WRITTEN     PIC 9(9) VALUE ZEROS.
           05  WS-ROWS-SKIPPED     PIC 9(9) VALUE ZEROS.

       01  WS-FLAGS.
           05  WS-DB2-EOF          PIC X    VALUE 'N'.
               88  DB2-EOF-REACHED VALUE 'Y'.

       01  WS-PROCESS-DATE         PIC X(8).
       01  WS-RETURN-CODE          PIC S9(4) COMP VALUE ZEROS.
       01  WS-SQLCODE-SAVE         PIC S9(9) COMP VALUE ZEROS.

      *----------------------------------------------------------------
      * DB2 host variables for CUST_ACCOUNT_MASTER cursor
      *----------------------------------------------------------------
       01  HV-CUST-ACCOUNT.
           05  HV-EXT-ACCT-NUM     PIC X(20).
           05  HV-SUB-ACCT-NUM     PIC X(10).
           05  HV-BOOK-ID          PIC X(6).
           05  HV-CUSTOMER-ID      PIC X(15).
           05  HV-PRODUCT-TYPE     PIC X(4).
           05  HV-RISK-SEGMENT     PIC X(3).
           05  HV-BEHAVIOUR-SCORE  PIC S9(4) COMP.
           05  HV-UNSECURED-IND    PIC X(1).
           05  HV-ACCT-OPEN-DATE   PIC X(8).
           05  HV-NEW-MAIN-ACCT    PIC X(20).
           05  HV-NEW-LOAN-ACCT    PIC X(20).
           05  HV-PROCESS-DATE     PIC X(8).

      *----------------------------------------------------------------
      * SQLCA - DB2 communication area
      *----------------------------------------------------------------
           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       PROCEDURE DIVISION.
      *================================================================
       MAIN-PARA.
           PERFORM INIT-PARA.
           PERFORM OPEN-CURSOR-PARA.
           PERFORM FETCH-LOOP-PARA UNTIL DB2-EOF-REACHED.
           PERFORM CLOSE-CURSOR-PARA.
           PERFORM CLOSE-FILES-PARA.
           PERFORM DISPLAY-TOTALS-PARA.
           MOVE WS-RETURN-CODE TO RETURN-CODE.
           STOP RUN.

      *================================================================
       INIT-PARA.
      *    Initialise counters and open output file
           MOVE ZEROS TO WS-COUNTERS.
           MOVE 'N'   TO WS-DB2-EOF.

           MOVE FUNCTION CURRENT-DATE(1:8) TO WS-PROCESS-DATE.

           OPEN OUTPUT EXTRACT-FILE.
           IF WS-EXTRACT-STATUS NOT = '00'
               DISPLAY 'CRDB2EXT: OPEN ERROR ON BHSCOEXT - STATUS='
                       WS-EXTRACT-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.

           DISPLAY 'CRDB2EXT: INIT COMPLETE. PROCESS-DATE=' WS-PROCESS-DATE.

      *================================================================
       OPEN-CURSOR-PARA.
      *    Declare and open DB2 cursor on CUST_ACCOUNT_MASTER
      *    Select all accounts active for behaviour scoring
           EXEC SQL
               DECLARE CSR_CUST_ACCT CURSOR FOR
               SELECT
                   TRIM(A.EXTERNAL_ACCOUNT_NUMBER),
                   TRIM(A.SUB_ACCOUNT_NUMBER),
                   TRIM(A.BOOK_ID),
                   TRIM(A.CUSTOMER_ID),
                   TRIM(A.PRODUCT_TYPE),
                   TRIM(A.RISK_SEGMENT),
                   A.BEHAVIOUR_SCORE,
                   TRIM(A.UNSECURED_IND),
                   VARCHAR_FORMAT(A.ACCOUNT_OPEN_DATE, 'YYYYMMDD'),
                   COALESCE(TRIM(A.NEW_MAIN_ACCOUNT_NUMBER), ' '),
                   COALESCE(TRIM(A.NEW_LOAN_ACCOUNT_NUMBER), ' '),
                   VARCHAR_FORMAT(CURRENT DATE, 'YYYYMMDD')
               FROM CRISK.CUST_ACCOUNT_MASTER A
               WHERE A.ACCOUNT_STATUS = 'A'
                 AND A.PRODUCT_TYPE IN ('LOAN', 'MORT', 'CRED', 'CURR')
                 AND A.SCORING_ELIGIBLE_IND = 'Y'
               ORDER BY A.EXTERNAL_ACCOUNT_NUMBER,
                        A.SUB_ACCOUNT_NUMBER
           END-EXEC.

           EXEC SQL
               OPEN CSR_CUST_ACCT
           END-EXEC.

           IF SQLCODE NOT = 0
               DISPLAY 'CRDB2EXT: CURSOR OPEN FAILED SQLCODE=' SQLCODE
               MOVE 8 TO WS-RETURN-CODE
               STOP RUN
           END-IF.

           DISPLAY 'CRDB2EXT: CURSOR OPENED ON CRISK.CUST_ACCOUNT_MASTER'.

      *================================================================
       FETCH-LOOP-PARA.
      *    Fetch one row at a time from DB2 cursor
           EXEC SQL
               FETCH CSR_CUST_ACCT
               INTO  :HV-EXT-ACCT-NUM,
                     :HV-SUB-ACCT-NUM,
                     :HV-BOOK-ID,
                     :HV-CUSTOMER-ID,
                     :HV-PRODUCT-TYPE,
                     :HV-RISK-SEGMENT,
                     :HV-BEHAVIOUR-SCORE,
                     :HV-UNSECURED-IND,
                     :HV-ACCT-OPEN-DATE,
                     :HV-NEW-MAIN-ACCT,
                     :HV-NEW-LOAN-ACCT,
                     :HV-PROCESS-DATE
           END-EXEC.

           EVALUATE SQLCODE
               WHEN 0
                   ADD 1 TO WS-ROWS-FETCHED
                   PERFORM WRITE-EXTRACT-PARA
               WHEN 100
                   MOVE 'Y' TO WS-DB2-EOF
               WHEN OTHER
                   MOVE SQLCODE TO WS-SQLCODE-SAVE
                   DISPLAY 'CRDB2EXT: FETCH ERROR SQLCODE='
                           WS-SQLCODE-SAVE
                   MOVE 8 TO WS-RETURN-CODE
                   MOVE 'Y' TO WS-DB2-EOF
           END-EVALUATE.

      *================================================================
       WRITE-EXTRACT-PARA.
      *    Move DB2 host variables to output record and write
           MOVE HV-EXT-ACCT-NUM  TO CRA-EXTERNAL-ACCT-NUM.
           MOVE HV-SUB-ACCT-NUM  TO CRA-SUB-ACCOUNT-NUM.
           MOVE HV-BOOK-ID       TO CRA-BOOK-ID.
           MOVE HV-CUSTOMER-ID   TO CRA-CUSTOMER-ID.
           MOVE HV-PRODUCT-TYPE  TO CRA-PRODUCT-TYPE.
           MOVE HV-RISK-SEGMENT  TO CRA-RISK-SEGMENT.
           MOVE HV-BEHAVIOUR-SCORE TO CRA-BEHAVIOUR-SCORE.
           MOVE HV-UNSECURED-IND TO CRA-UNSECURED-IND.
           MOVE HV-ACCT-OPEN-DATE TO CRA-ACCOUNT-OPEN-DATE.
           MOVE HV-NEW-MAIN-ACCT TO CRA-NEW-MAIN-ACCT-NUM.
           MOVE HV-NEW-LOAN-ACCT TO CRA-NEW-LOAN-ACCT-NUM.
           MOVE HV-PROCESS-DATE  TO CRA-PROCESS-DATE.

           WRITE CR-CUST-ACCOUNT-REC.
           IF WS-EXTRACT-STATUS NOT = '00'
               DISPLAY 'CRDB2EXT: WRITE ERROR - STATUS='
                       WS-EXTRACT-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.
           ADD 1 TO WS-ROWS-WRITTEN.

      *================================================================
       CLOSE-CURSOR-PARA.
           EXEC SQL
               CLOSE CSR_CUST_ACCT
           END-EXEC.

           IF SQLCODE NOT = 0
               DISPLAY 'CRDB2EXT: CURSOR CLOSE WARNING SQLCODE=' SQLCODE
           END-IF.

      *================================================================
       CLOSE-FILES-PARA.
           CLOSE EXTRACT-FILE.
           IF WS-EXTRACT-STATUS NOT = '00'
               DISPLAY 'CRDB2EXT: CLOSE ERROR ON BHSCOEXT STATUS='
                       WS-EXTRACT-STATUS
           END-IF.

      *================================================================
       DISPLAY-TOTALS-PARA.
           DISPLAY '**CRDB2EXT TOTALS**'.
           DISPLAY '  DB2 TABLE READ  : CRISK.CUST_ACCOUNT_MASTER'.
           DISPLAY '  OUTPUT DATASET  : CUST.BHSCORE.EXTRACT'.
           DISPLAY '  ROWS FETCHED    : ' WS-ROWS-FETCHED.
           DISPLAY '  ROWS WRITTEN    : ' WS-ROWS-WRITTEN.
           DISPLAY '  ROWS SKIPPED    : ' WS-ROWS-SKIPPED.
           DISPLAY '  RETURN CODE     : ' WS-RETURN-CODE.
