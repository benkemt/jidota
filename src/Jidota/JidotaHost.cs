using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Jidota;

/// <summary>
/// The generic host of the running instance (Microsoft.Extensions.Hosting, built-in DI —
/// ARCHITECTURE.md §2.2). The poller and the job loop are hosted services in the same host as the
/// web app; each later ticket registers its services in <see cref="ConfigureServices"/>.
/// It is built only by the commands that need it (`serve`, ticket 32), never for `--help`.
/// </summary>
internal static class JidotaHost
{
    public static HostApplicationBuilder CreateBuilder(string[] args)
    {
        var builder = Host.CreateApplicationBuilder(args);
        ConfigureServices(builder.Services);
        return builder;
    }

    internal static void ConfigureServices(IServiceCollection services)
    {
        // Registrations are added by the tickets that own each module.
    }
}
