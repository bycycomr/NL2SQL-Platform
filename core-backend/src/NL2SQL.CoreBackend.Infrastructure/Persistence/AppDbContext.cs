using Microsoft.EntityFrameworkCore;
using NL2SQL.CoreBackend.Domain.Entities;

namespace NL2SQL.CoreBackend.Infrastructure.Persistence;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<User> Users => Set<User>();
    public DbSet<QueryHistory> QueryHistories => Set<QueryHistory>();
    public DbSet<SchemaCache> SchemaCaches => Set<SchemaCache>();
    public DbSet<DatabaseConnection> DatabaseConnections => Set<DatabaseConnection>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<User>(entity =>
        {
            entity.ToTable("users");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Email).IsRequired().HasMaxLength(255);
            entity.HasIndex(e => e.Email).IsUnique();
            entity.Property(e => e.PasswordHash).IsRequired();
            entity.Property(e => e.FullName).IsRequired().HasMaxLength(200);
            entity.Property(e => e.Role).HasConversion<string>().HasMaxLength(20);
        });

        modelBuilder.Entity<DatabaseConnection>(entity =>
        {
            entity.ToTable("database_connections");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.DbId).IsRequired().HasMaxLength(100);
            entity.HasIndex(e => e.DbId);
            entity.Property(e => e.DisplayName).IsRequired().HasMaxLength(200);
            entity.Property(e => e.ConnectionString).IsRequired();
            entity.Property(e => e.Provider).HasConversion<string>().HasMaxLength(20);

            entity.HasOne(e => e.User)
                  .WithMany(u => u.DatabaseConnections)
                  .HasForeignKey(e => e.UserId)
                  .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<QueryHistory>(entity =>
        {
            entity.ToTable("query_history");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.NaturalLanguageQuery).IsRequired();
            entity.Property(e => e.DbId).HasMaxLength(100);
            entity.Property(e => e.ExecutionStatus).HasConversion<string>().HasMaxLength(20);
            entity.Property(e => e.ResultDataJson).HasColumnType("jsonb");
            entity.HasIndex(e => e.UserId);
            entity.HasIndex(e => e.CreatedAt).IsDescending();

            entity.HasOne(e => e.User)
                  .WithMany(u => u.QueryHistories)
                  .HasForeignKey(e => e.UserId)
                  .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<SchemaCache>(entity =>
        {
            entity.ToTable("schema_cache");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.DbId).IsRequired().HasMaxLength(100);
            entity.HasIndex(e => e.DbId);
            entity.Property(e => e.DatabaseName).IsRequired().HasMaxLength(255);
            entity.Property(e => e.SchemaJson).HasColumnType("jsonb");
            entity.HasIndex(e => e.ExpiresAt);
        });
    }

    public override Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
    {
        foreach (var entry in ChangeTracker.Entries<Domain.Common.BaseEntity>())
        {
            if (entry.State == EntityState.Modified)
                entry.Entity.UpdatedAt = DateTime.UtcNow;
        }

        return base.SaveChangesAsync(cancellationToken);
    }
}
