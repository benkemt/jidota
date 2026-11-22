using System.Text.RegularExpressions;
using YamlDotNet.Core;
using YamlDotNet.Serialization;

namespace TicketGraph;

public sealed class Ticket
{
    public const string HumanTag = "[HUMAN]";

    public required string Id { get; init; }
    public string? Key { get; init; }
    public required string Title { get; init; }
    public required IReadOnlyList<string> DependsOn { get; init; }
    public string? BaseCommit { get; init; }
    public string? StartBranch { get; init; }
    public required IReadOnlyList<string> Touches { get; init; }
    public required string Path { get; init; }

    /// <summary>Dépendances résolues en ids, remplies par <see cref="Graph.Load"/>.</summary>
    public SortedSet<string> Deps { get; } = new(StringComparer.Ordinal);

    public bool Human => Title.Contains(HumanTag, StringComparison.Ordinal);
}

public sealed class TicketFormatException(string message) : Exception(message);

public static partial class TicketParser
{
    [GeneratedRegex(@"```ya?ml\s*\n(.*?)```", RegexOptions.Singleline)]
    private static partial Regex YamlBlock();

    [GeneratedRegex(@"^#\s+(.+)$", RegexOptions.Multiline)]
    private static partial Regex TitleLine();

    private static readonly IDeserializer Yaml = new DeserializerBuilder().Build();

    public static Ticket Parse(string path)
    {
        var name = System.IO.Path.GetFileName(path);
        var text = File.ReadAllText(path).ReplaceLineEndings("\n");
        var block = YamlBlock().Match(text);
        if (!block.Success)
            throw new TicketFormatException($"{name}: aucun bloc ```yaml``` trouvé");

        var meta = ReadMapping(block.Groups[1].Value, name);
        if (!meta.TryGetValue("id", out var id))
            throw new TicketFormatException($"{name}: champ 'id' manquant");

        var title = TitleLine().Match(text);
        return new Ticket
        {
            Id = id?.ToString() ?? "None",
            Key = NonEmpty(meta, "key"),
            Title = title.Success ? title.Groups[1].Value.Trim() : System.IO.Path.GetFileNameWithoutExtension(path),
            DependsOn = Strings(meta, "depends_on"),
            BaseCommit = NonEmpty(meta, "base_commit"),
            StartBranch = meta.GetValueOrDefault("start_branch")?.ToString(),
            Touches = Strings(meta, "touches"),
            Path = path,
        };
    }

    private static Dictionary<string, object?> ReadMapping(string yaml, string name)
    {
        object? root;
        try
        {
            root = Yaml.Deserialize<object?>(yaml);
        }
        catch (YamlException e)
        {
            throw new TicketFormatException($"{name}: bloc yaml illisible ({e.Message})");
        }
        return root switch
        {
            null => [],
            IDictionary<object, object?> map => map.ToDictionary(kv => kv.Key.ToString()!, kv => kv.Value),
            _ => throw new TicketFormatException($"{name}: le bloc yaml n'est pas un dictionnaire"),
        };
    }

    private static string? NonEmpty(Dictionary<string, object?> meta, string field) =>
        meta.GetValueOrDefault(field)?.ToString() is { Length: > 0 } s ? s : null;

    private static List<string> Strings(Dictionary<string, object?> meta, string field) =>
        meta.GetValueOrDefault(field) is IEnumerable<object?> items
            ? items.Select(i => i?.ToString() ?? "None").ToList()
            : [];
}
