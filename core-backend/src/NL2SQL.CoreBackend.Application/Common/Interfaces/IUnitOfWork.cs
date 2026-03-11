using NL2SQL.CoreBackend.Domain.Entities;

namespace NL2SQL.CoreBackend.Application.Common.Interfaces;

public interface IUnitOfWork : IDisposable
{
    IRepository<User> Users { get; }
    IRepository<QueryHistory> QueryHistories { get; }
    IRepository<SchemaCache> SchemaCaches { get; }
    IRepository<DatabaseConnection> DatabaseConnections { get; }

    Task<int> SaveChangesAsync(CancellationToken ct = default);
}
