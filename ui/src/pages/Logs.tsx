import { Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ScrollText, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { clearLogs, getLogStats, getLogs, type ScreenEvent } from "@/lib/api";
import { GATE_SHORT } from "@/lib/gates";

const ACTION_STYLES: Record<string, string> = {
  pass: "border-primary/25 bg-primary/15 text-primary",
  mask: "border-primary/25 bg-primary/15 text-primary",
  block: "border-red-500/25 bg-red-500/15 text-red-500",
  flag: "border-primary/25 bg-primary/15 text-primary",
};

function Tile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export default function Logs() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  const { data: logs } = useQuery({
    queryKey: ["logs"],
    queryFn: () => getLogs(200),
    refetchInterval: 2000,
  });
  const { data: stats } = useQuery({
    queryKey: ["logStats"],
    queryFn: getLogStats,
    refetchInterval: 2000,
  });

  const clear = useMutation({
    mutationFn: clearLogs,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["logs"] });
      void queryClient.invalidateQueries({ queryKey: ["logStats"] });
    },
  });

  const events: ScreenEvent[] = logs?.events ?? [];
  const visible = filter === "all" ? events : events.filter((e) => e.action === filter);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">Logs</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            The last 1000 screening calls, held in memory. Cleared on restart.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All actions</SelectItem>
              <SelectItem value="pass">Pass</SelectItem>
              <SelectItem value="mask">Mask</SelectItem>
              <SelectItem value="block">Block</SelectItem>
              <SelectItem value="flag">Flag</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => clear.mutate()}
            disabled={!events.length}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile label="Total" value={stats?.total ?? 0} />
        <Tile
          label="Caught"
          value={stats?.caught ?? 0}
          hint={
            stats?.total
              ? `${stats.blocked} blocked · ${stats.masked} masked · ${stats.flagged} flagged`
              : undefined
          }
        />
        <Tile label="PII hits" value={stats?.pii_total ?? 0} />
        <Tile
          label="Latency"
          value={`${stats?.avg_latency_ms ?? 0}ms`}
          hint={stats?.p95_latency_ms ? `p95 ${stats.p95_latency_ms}ms` : "avg"}
        />
      </div>

      {!logs?.store_text && (
        <p className="text-xs text-muted-foreground">
          Request text is not recorded. Start the server with{" "}
          <code className="font-mono">--log-text</code> to include it.
        </p>
      )}

      <Card>
        <CardContent className="p-0">
          {visible.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <ScrollText className="mb-3 h-10 w-10 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                No screening calls yet. Run one from the Playground.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-28">Time</TableHead>
                  <TableHead className="w-20">Stage</TableHead>
                  <TableHead className="w-24">Action</TableHead>
                  <TableHead className="w-56">Caught by</TableHead>
                  <TableHead className="w-52">Decided by</TableHead>
                  <TableHead>PII</TableHead>
                  <TableHead className="w-24 text-right">Latency</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((e, i) => (
                  <Fragment key={`${e.ts}-${i}`}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setExpanded(expanded === i ? null : i)}
                    >
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {new Date(e.ts * 1000).toLocaleTimeString()}
                      </TableCell>
                      <TableCell className="text-xs">{e.stage}</TableCell>
                      <TableCell>
                        <Badge
                          className={cn(
                            "font-mono text-[10px] uppercase",
                            ACTION_STYLES[e.action],
                          )}
                        >
                          {e.action}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {e.flagged?.length ? (
                          <span className="flex flex-wrap gap-1">
                            {e.flagged.map((g) => (
                              <span
                                key={g}
                                className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-foreground"
                              >
                                {GATE_SHORT[g] ?? g}
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs">
                        {e.decided_by ? (
                          <span
                            className={cn(
                              "inline-flex items-center gap-1.5",
                              e.degraded ? "text-amber-600" : "text-muted-foreground",
                            )}
                          >
                            {e.degraded && (
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                            )}
                            {e.decided_by}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {e.pii_count > 0
                          ? `${e.pii_count} · ${e.pii_labels.slice(0, 2).join(", ")}${
                              e.pii_labels.length > 2 ? "…" : ""
                            }`
                          : "-"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {e.latency_ms}ms
                      </TableCell>
                    </TableRow>
                    {expanded === i && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={7} className="bg-muted/40">
                          <div className="space-y-2 py-2 text-xs">
                            <div className="flex flex-wrap gap-4">
                              {Object.entries(e.gates).map(([gate, ms]) => (
                                <span key={gate} className="font-mono text-muted-foreground">
                                  {gate}: {ms.toFixed(1)}ms
                                </span>
                              ))}
                            </div>
                            {e.request_id && (
                              <p className="font-mono text-muted-foreground">
                                request_id: {e.request_id}
                              </p>
                            )}
                            {e.text && (
                              <p className="whitespace-pre-wrap break-words rounded bg-background p-2 font-mono">
                                {e.text}
                              </p>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
