// Construit le graphe de dépendances des tickets à partir de leur bloc YAML.
// Portage .NET de ticket_graph.py : mêmes règles, mêmes messages, mêmes codes de sortie.

using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using TicketGraph;

const string Usage = """
    usage: ticket-graph <folder> [--merged IDS] [--in-progress IDS] [--mermaid] [--json]

    Construit le graphe de dépendances des tickets à partir de leur bloc YAML.

    Usage :
        ticket-graph tickets/                     # graphe + vagues + frontière
        ticket-graph tickets/ --merged T1         # frontière une fois T1 fusionné
        ticket-graph tickets/ --mermaid           # diagramme Mermaid
        ticket-graph tickets/ --json              # sortie machine pour l'orchestrateur

    Codes de sortie : 0 = graphe valide, 2 = graphe invalide (cycle, référence inconnue...).

    options:
      --merged IDS       ids fusionnés, séparés par des virgules
      --in-progress IDS  ids en cours, séparés par des virgules
      --mermaid
      --json
    """;

Console.OutputEncoding = new UTF8Encoding(false);

if (!TryParseArgs(args, out var options, out var argError))
{
    if (argError is null)
    {
        Console.WriteLine(Usage);
        return 0;
    }
    Console.Error.WriteLine(Usage.Split('\n')[0]);
    Console.Error.WriteLine($"ticket-graph: error: {argError}");
    return 2;
}

var (tickets, errors) = Graph.Load(options.Folder);
var plan = new List<List<string>>();
if (errors.Count == 0)
{
    try
    {
        plan = Graph.Waves(tickets);
    }
    catch (CycleException e)
    {
        errors.Add(e.Message);
    }
}
if (errors.Count > 0)
{
    Console.Error.WriteLine("Graphe invalide :");
    foreach (var e in errors)
        Console.Error.WriteLine($"  - {e}");
    return 2;
}

var merged = SplitIds(options.Merged);
var inProgress = SplitIds(options.InProgress);
var ready = Graph.Frontier(tickets, merged, inProgress);
var agents = ready.Where(t => !tickets[t].Human).ToList();
var humans = ready.Where(t => tickets[t].Human).ToList();
var warnings = Graph.TouchConflicts(tickets, agents);

if (options.Json)
{
    var document = new
    {
        waves = plan,
        frontier = new { agents, humans },
        warnings,
        tickets = tickets.Values.ToDictionary(
            t => t.Id,
            t => new { key = t.Key, deps = t.Deps.ToList(), human = t.Human, file = t.Path }),
    };
    Console.WriteLine(JsonSerializer.Serialize(document, new JsonSerializerOptions
    {
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    }));
}
else if (options.Mermaid)
{
    Console.WriteLine(Graph.Mermaid(tickets, merged, ready).ReplaceLineEndings());
}
else
{
    Console.WriteLine("Vagues (ordre topologique) :");
    for (var i = 0; i < plan.Count; i++)
        Console.WriteLine($"  {i + 1}. " + string.Join(", ", plan[i].Select(t => t + (tickets[t].Human ? " [HUMAN]" : ""))));
    Console.WriteLine();
    Console.WriteLine($"Frontière (fusionnés : {(merged.Count > 0 ? Repr.List(merged) : "aucun")}) :");
    Console.WriteLine($"  -> sous-agents : {(agents.Count > 0 ? Repr.List(agents) : "-")}");
    Console.WriteLine($"  -> humain      : {(humans.Count > 0 ? Repr.List(humans) : "-")}");
    foreach (var w in warnings)
        Console.WriteLine($"  ! {w}");
}
return 0;

static HashSet<string> SplitIds(string value) =>
    value.Split(',').Where(s => s.Length > 0).ToHashSet(StringComparer.Ordinal);

// Retourne false avec error == null pour --help, false avec un message pour une erreur d'usage.
static bool TryParseArgs(string[] args, out Options options, out string? error)
{
    options = new Options();
    error = null;
    string? folder = null;
    for (var i = 0; i < args.Length; i++)
    {
        var arg = args[i];
        var (name, inline) = arg.StartsWith("--") && arg.Contains('=')
            ? (arg[..arg.IndexOf('=')], arg[(arg.IndexOf('=') + 1)..])
            : (arg, null);
        switch (name)
        {
            case "-h" or "--help":
                return false;
            case "--mermaid":
                options = options with { Mermaid = true };
                break;
            case "--json":
                options = options with { Json = true };
                break;
            case "--merged" or "--in-progress":
                var value = inline ?? (i + 1 < args.Length ? args[++i] : null);
                if (value is null)
                {
                    error = $"argument {name}: expected one argument";
                    return false;
                }
                options = name == "--merged" ? options with { Merged = value } : options with { InProgress = value };
                break;
            case var _ when arg.StartsWith('-') && arg.Length > 1:
                error = $"unrecognized arguments: {arg}";
                return false;
            default:
                if (folder is not null)
                {
                    error = $"unrecognized arguments: {arg}";
                    return false;
                }
                folder = arg;
                break;
        }
    }
    if (folder is null)
    {
        error = "the following arguments are required: folder";
        return false;
    }
    options = options with { Folder = folder };
    return true;
}

internal sealed record Options(
    string Folder = "", string Merged = "", string InProgress = "", bool Mermaid = false, bool Json = false);
