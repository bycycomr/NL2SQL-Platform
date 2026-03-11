using NL2SQL.CoreBackend.Domain.Common;
using NL2SQL.CoreBackend.Domain.Enums;

namespace NL2SQL.CoreBackend.Domain.Entities;

public class DatabaseConnection : BaseEntity
{
    public Guid UserId { get; set; }
    public string DbId { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public string ConnectionString { get; set; } = string.Empty;
    public DatabaseProvider Provider { get; set; } = DatabaseProvider.PostgreSQL;
    public bool IsActive { get; set; } = true;

    public User User { get; set; } = null!;
}
