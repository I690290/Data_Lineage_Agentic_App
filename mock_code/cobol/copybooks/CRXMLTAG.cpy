      *================================================================
      * COPYBOOK : CRXMLTAG.cpy
      * SYSTEM   : Credit Risk Behaviour Scoring System
      * PURPOSE  : XML tag literal definitions for MI4014 extract
      *            Used by CRXMLGEN to build XML output
      *================================================================
       01  CR-XML-TAGS.
           05  CXMT-ITEM-OPEN          PIC X(6)   VALUE '<Item>'.
           05  CXMT-ITEM-CLOSE         PIC X(7)   VALUE '</Item>'.
           05  CXMT-EXT-ACCT-OPEN      PIC X(27)
               VALUE '<external_account_number>'.
           05  CXMT-EXT-ACCT-CLOSE     PIC X(28)
               VALUE '</external_account_number>'.
           05  CXMT-SUB-NO-OPEN        PIC X(7)   VALUE '<sub_no>'.
           05  CXMT-SUB-NO-CLOSE       PIC X(8)   VALUE '</sub_no>'.
           05  CXMT-BOOK-ID-OPEN       PIC X(8)   VALUE '<book_id>'.
           05  CXMT-BOOK-ID-CLOSE      PIC X(9)   VALUE '</book_id>'.
           05  CXMT-TRAN-CODE-OPEN     PIC X(17)
               VALUE '<transaction_code>'.
           05  CXMT-TRAN-CODE-CLOSE    PIC X(18)
               VALUE '</transaction_code>'.
           05  CXMT-TRAN-AMT-OPEN      PIC X(16)
               VALUE '<transaction_amt>'.
           05  CXMT-TRAN-AMT-CLOSE     PIC X(17)
               VALUE '</transaction_amt>'.
           05  CXMT-TRAN-CAT-OPEN      PIC X(15)
               VALUE '<tran_category>'.
           05  CXMT-TRAN-CAT-CLOSE     PIC X(16)
               VALUE '</tran_category>'.
           05  CXMT-POSTED-DT-OPEN     PIC X(13)
               VALUE '<posted_date>'.
           05  CXMT-POSTED-DT-CLOSE    PIC X(14)
               VALUE '</posted_date>'.
           05  CXMT-EFFEC-DT-OPEN      PIC X(16)
               VALUE '<effective_date>'.
           05  CXMT-EFFEC-DT-CLOSE     PIC X(17)
               VALUE '</effective_date>'.
           05  CXMT-UNSEC-OPEN         PIC X(11)  VALUE '<unsec_ind>'.
           05  CXMT-UNSEC-CLOSE        PIC X(12)  VALUE '</unsec_ind>'.
           05  CXMT-NEW-MAIN-OPEN      PIC X(25)
               VALUE '<New_Main_Account_Number>'.
           05  CXMT-NEW-MAIN-CLOSE     PIC X(26)
               VALUE '</New_Main_Account_Number>'.
           05  CXMT-NEW-LOAN-OPEN      PIC X(25)
               VALUE '<New_Loan_Account_Number>'.
           05  CXMT-NEW-LOAN-CLOSE     PIC X(26)
               VALUE '</New_Loan_Account_Number>'.
