using NL2SQL.CoreBackend.Application.Common.Interfaces;
using NL2SQL.CoreBackend.Domain.Entities;

namespace NL2SQL.CoreBackend.Infrastructure.Persistence;

public class UnitOfWork : IUnitOfWork
{
    private readonly AppDbContext _context;

    private IRepository<User>? _users;
    private IRepository<QueryHistory>? _queryHistories;
    private IRepository<SchemaCache>? _schemaCaches;
    private IRepository<DatabaseConnection>? _databaseConnections;

    public UnitOfWork(AppDbContext context)
    {
        _context = context;
    }

    public IRepository<User> Users
        => _users ??= new EfRepository<User>(_context);

    public IRepository<QueryHistory> QueryHistories
        => _queryHistories ??= new EfRepository<QueryHistory>(_context);

    public IRepository<SchemaCache> SchemaCaches
        => _schemaCaches ??= new EfRepository<SchemaCache>(_context);

    public IRepository<DatabaseConnection> DatabaseConnections
        => _databaseConnections ??= new EfRepository<DatabaseConnection>(_context);

    public async Task<int> SaveChangesAsync(CancellationToken ct = default)
        => await _context.SaveChangesAsync(ct);

    public void Dispose()
    {
        _context.Dispose();
        GC.SuppressFinalize(this);
    }
}
