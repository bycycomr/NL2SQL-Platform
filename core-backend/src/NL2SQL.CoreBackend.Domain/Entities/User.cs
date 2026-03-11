using NL2SQL.CoreBackend.Domain.Common;
using NL2SQL.CoreBackend.Domain.Enums;

namespace NL2SQL.CoreBackend.Domain.Entities;

public class User : BaseEntity
{
    public string Email { get; set; } = string.Empty;
    public string PasswordHash { get; set; } = string.Empty;
    public string FullName { get; set; } = string.Empty;
    public UserRole Role { get; set; } = UserRole.Viewer;
    public bool IsActive { get; set; } = true;

    public ICollection<QueryHistory> QueryHistories { get; set; } = [];
    public ICollection<DatabaseConnection> DatabaseConnections { get; set; } = [];
}
