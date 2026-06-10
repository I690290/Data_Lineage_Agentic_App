      *  ACCT-REC.CPY - Account Record Copybook
      *  Defines the layout of ACCOUNT-MASTER-FILE records
       05  AM-ACCOUNT-NUMBER    PIC 9(10).
       05  AM-CUSTOMER-NAME     PIC X(40).
       05  AM-ACCOUNT-TYPE      PIC X(5).
           88  ACCT-CHECKING    VALUE 'CHKNG'.
           88  ACCT-SAVINGS     VALUE 'SAVNG'.
           88  ACCT-CREDIT      VALUE 'CRDIT'.
           88  ACCT-LOAN        VALUE 'LOAN '.
       05  AM-BALANCE           PIC S9(13)V99 COMP-3.
       05  AM-OPEN-DATE         PIC X(8).
       05  AM-STATUS-CODE       PIC X(2).
           88  ACCT-ACTIVE      VALUE 'AC'.
           88  ACCT-INACTIVE    VALUE 'IN'.
           88  ACCT-CLOSED      VALUE 'CL'.
           88  ACCT-SUSPENDED   VALUE 'SU'.
       05  AM-CREDIT-LIMIT      PIC S9(11)V99 COMP-3.
       05  AM-BRANCH-CODE       PIC X(4).
       05  AM-PRODUCT-CODE      PIC X(6).
       05  AM-LAST-ACTIVITY-DT  PIC X(8).
       05  AM-INTEREST-RATE     PIC S9(3)V9999 COMP-3.
       05  AM-FILLER            PIC X(75).
