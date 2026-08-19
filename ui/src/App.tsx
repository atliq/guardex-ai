import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AppShell } from "@/components/AppShell";
import Playground from "@/pages/Playground";
import Logs from "@/pages/Logs";
import Config from "@/pages/Config";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<Playground />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/config" element={<Config />} />
          </Routes>
        </AppShell>
        <Toaster />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
