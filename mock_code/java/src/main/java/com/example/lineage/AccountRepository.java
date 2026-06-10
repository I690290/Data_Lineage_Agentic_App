package com.example.lineage;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * AccountRepository — JPA repository for ACCOUNT_SUMMARY table.
 * Table is populated by the COBOL→SQL pipeline (PROG001 → load_accounts.sql).
 */
@Repository
public interface AccountRepository extends JpaRepository<AccountSummary, Long> {

    Optional<AccountSummary> findByAccountNumber(Long accountNumber);

    List<AccountSummary> findByStatusCode(String statusCode);

    List<AccountSummary> findByBranchCode(String branchCode);

    @Query("SELECT a FROM AccountSummary a WHERE a.balance < :threshold AND a.statusCode = 'AC'")
    List<AccountSummary> findAccountsBelowBalance(@Param("threshold") BigDecimal threshold);

    @Query(value = """
            SELECT a.* FROM ACCOUNT_SUMMARY a
            WHERE a.STATUS_CODE = :status
            ORDER BY a.ACCOUNT_NUMBER
            """, nativeQuery = true)
    List<AccountSummary> findByStatusNative(@Param("status") String status);

    @Query(value = """
            SELECT a.ACCOUNT_NUMBER, a.CUSTOMER_NAME, a.BALANCE,
                   COUNT(t.TRANSACTION_ID) AS TX_COUNT
            FROM ACCOUNT_SUMMARY a
            LEFT JOIN TRANSACTION_DETAIL t ON a.ACCOUNT_NUMBER = t.ACCOUNT_NUMBER
            GROUP BY a.ACCOUNT_NUMBER, a.CUSTOMER_NAME, a.BALANCE
            HAVING COUNT(t.TRANSACTION_ID) > :minTransactions
            """, nativeQuery = true)
    List<Object[]> findAccountsWithTransactionCount(@Param("minTransactions") int minTransactions);
}


/**
 * AccountSummary entity — maps to ACCOUNT_SUMMARY table.
 * Populated by SQL load_accounts.sql (sourced from COBOL PROG001 output).
 */
@Entity
@Table(name = "ACCOUNT_SUMMARY")
class AccountSummary {

    @Id
    @Column(name = "ACCOUNT_NUMBER")
    private Long accountNumber;

    @Column(name = "CUSTOMER_NAME", length = 40)
    private String customerName;

    @Column(name = "ACCOUNT_TYPE", length = 5)
    private String accountType;

    @Column(name = "BALANCE", precision = 15, scale = 2)
    private BigDecimal balance;

    @Column(name = "OPEN_DATE")
    private LocalDate openDate;

    @Column(name = "STATUS_CODE", length = 2)
    private String statusCode;

    @Column(name = "CREDIT_LIMIT", precision = 13, scale = 2)
    private BigDecimal creditLimit;

    @Column(name = "BRANCH_CODE", length = 4)
    private String branchCode;

    @Column(name = "PRODUCT_CODE", length = 6)
    private String productCode;

    @Column(name = "LAST_UPDATED")
    private LocalDateTime lastUpdated;

    // Getters and setters
    public Long getAccountNumber() { return accountNumber; }
    public void setAccountNumber(Long v) { this.accountNumber = v; }
    public String getCustomerName() { return customerName; }
    public void setCustomerName(String v) { this.customerName = v; }
    public String getAccountType() { return accountType; }
    public void setAccountType(String v) { this.accountType = v; }
    public BigDecimal getBalance() { return balance; }
    public void setBalance(BigDecimal v) { this.balance = v; }
    public LocalDate getOpenDate() { return openDate; }
    public void setOpenDate(LocalDate v) { this.openDate = v; }
    public String getStatusCode() { return statusCode; }
    public void setStatusCode(String v) { this.statusCode = v; }
    public BigDecimal getCreditLimit() { return creditLimit; }
    public void setCreditLimit(BigDecimal v) { this.creditLimit = v; }
    public String getBranchCode() { return branchCode; }
    public void setBranchCode(String v) { this.branchCode = v; }
    public String getProductCode() { return productCode; }
    public void setProductCode(String v) { this.productCode = v; }
    public LocalDateTime getLastUpdated() { return lastUpdated; }
    public void setLastUpdated(LocalDateTime v) { this.lastUpdated = v; }
}
