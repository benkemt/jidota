namespace TicketGraph;

public sealed class CycleException(IReadOnlyList<string> cycle)
    : Exception($"cycle détecté : {string.Join(" -> ", cycle)}")
{
    public IReadOnlyList<string> Cycle { get; } = cycle;
}

public static class Graph
{
    /// <summary>Charge les tickets et résout les dépendances. Retourne (tickets, erreurs).</summary>
    public static (Dictionary<string, Ticket> Tickets, List<string> Errors) Load(string folder)
    {
        var errors = new List<string>();
        var tickets = new Dictionary<string, Ticket>(StringComparer.Ordinal);
        IEnumerable<string> files = Directory.Exists(folder)
            ? Directory.EnumerateFiles(folder)
                .Where(p => System.IO.Path.GetExtension(p).Equals(".md", StringComparison.OrdinalIgnoreCase))
                .Select(p => p.Replace(System.IO.Path.AltDirectorySeparatorChar, System.IO.Path.DirectorySeparatorChar))
                .Order(StringComparer.Ordinal)
            : [];

        foreach (var p in files)
        {
            Ticket t;
            try
            {
                t = TicketParser.Parse(p);
            }
            catch (TicketFormatException e)
            {
                errors.Add(e.Message);
                continue;
            }
            if (tickets.ContainsKey(t.Id))
                errors.Add($"id en double : {t.Id}");
            tickets[t.Id] = t;
        }

        // Une dépendance peut viser l'id local (T1) ou la clé du tracker (ABB-33).
        var alias = tickets.Values.ToDictionary(t => t.Id, t => t.Id, StringComparer.Ordinal);
        foreach (var t in tickets.Values.Where(t => t.Key is not null))
            alias[t.Key!] = t.Id;

        foreach (var t in tickets.Values)
        {
            foreach (var reference in t.DependsOn)
            {
                if (!alias.TryGetValue(reference, out var target))
                    errors.Add($"{t.Id}: dépend de '{reference}', inconnu dans ce lot");
                else if (target == t.Id)
                    errors.Add($"{t.Id}: dépend de lui-même");
                else
                    t.Deps.Add(target);
            }
        }

        var branches = tickets.Values.Select(t => t.StartBranch).Distinct().ToList();
        if (branches.Count > 1)
            errors.Add($"start_branch incohérentes : {Repr.List(branches.Select(b => b ?? "None"))}");
        return (tickets, errors);
    }

    /// <summary>Vagues successives : chaque vague ne dépend que des précédentes. Lève <see cref="CycleException"/>.</summary>
    public static List<List<string>> Waves(IReadOnlyDictionary<string, Ticket> tickets)
    {
        var result = new List<List<string>>();
        var placed = new HashSet<string>(StringComparer.Ordinal);
        while (placed.Count < tickets.Count)
        {
            var ready = tickets.Values
                .Where(t => !placed.Contains(t.Id) && t.Deps.All(placed.Contains))
                .Select(t => t.Id)
                .Order(StringComparer.Ordinal)
                .ToList();
            if (ready.Count == 0)
                throw new CycleException(FindCycle(tickets, placed));
            result.Add(ready);
            placed.UnionWith(ready);
        }
        return result;
    }

    /// <summary>
    /// Chaque ticket restant a au moins une dépendance non placée : en suivant toujours la plus petite,
    /// on retombe forcément sur un ticket déjà vu. Le chemin est rendu dans le sens dépendance -> dépendant.
    /// </summary>
    private static List<string> FindCycle(IReadOnlyDictionary<string, Ticket> tickets, HashSet<string> placed)
    {
        var path = new List<string>();
        var node = tickets.Keys.Where(id => !placed.Contains(id)).Order(StringComparer.Ordinal).First();
        while (!path.Contains(node))
        {
            path.Add(node);
            node = tickets[node].Deps.First(d => !placed.Contains(d));
        }
        var cycle = path[path.IndexOf(node)..];
        cycle.Add(node);
        cycle.Reverse();
        return cycle;
    }

    /// <summary>Tickets non commencés dont toutes les dépendances sont fusionnées.</summary>
    public static List<string> Frontier(
        IReadOnlyDictionary<string, Ticket> tickets, ISet<string> merged, ISet<string> inProgress) =>
        tickets.Values
            .Where(t => !merged.Contains(t.Id) && !inProgress.Contains(t.Id) && t.Deps.IsSubsetOf(merged))
            .Select(t => t.Id)
            .Order(StringComparer.Ordinal)
            .ToList();

    /// <summary>Fichiers modifiés par plusieurs tickets lancés en parallèle (risque de conflit de merge).</summary>
    public static List<string> TouchConflicts(IReadOnlyDictionary<string, Ticket> tickets, IReadOnlyList<string> ids)
    {
        var warnings = new List<string>();
        for (var i = 0; i < ids.Count; i++)
        {
            for (var j = i + 1; j < ids.Count; j++)
            {
                var (a, b) = (ids[i], ids[j]);
                var common = tickets[a].Touches.Intersect(tickets[b].Touches).ToList();
                if (common.Count > 0)
                    warnings.Add($"{a} et {b} touchent tous les deux {Repr.List(common)}");
            }
        }
        return warnings;
    }

    public static string Mermaid(IReadOnlyDictionary<string, Ticket> tickets, ISet<string> merged, IReadOnlyList<string> ready)
    {
        var lines = new List<string> { "graph LR" };
        foreach (var t in tickets.Values)
        {
            var label = $"{t.Id} {t.Key}".Trim();
            lines.Add(t.Human ? $"    {t.Id}[/\"{label}\"/]" : $"    {t.Id}[\"{label}\"]");
        }
        foreach (var t in tickets.Values)
        {
            foreach (var d in t.Deps)
                lines.Add($"    {d} --> {t.Id}");
        }
        lines.Add("    classDef merged fill:#d3f9d8,stroke:#2b8a3e");
        lines.Add("    classDef ready fill:#fff3bf,stroke:#e67700");
        if (merged.Count > 0)
            lines.Add($"    class {string.Join(',', merged.Order(StringComparer.Ordinal))} merged");
        if (ready.Count > 0)
            lines.Add($"    class {string.Join(',', ready)} ready");
        return string.Join('\n', lines);
    }
}

/// <summary>Rendu des listes au format de Python (<c>['T1', 'T3']</c>) pour garder les mêmes messages.</summary>
public static class Repr
{
    public static string List(IEnumerable<string> items) =>
        "[" + string.Join(", ", items.Order(StringComparer.Ordinal).Select(s => $"'{s}'")) + "]";
}
