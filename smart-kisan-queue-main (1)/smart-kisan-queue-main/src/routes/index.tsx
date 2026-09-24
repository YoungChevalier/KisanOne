import { createFileRoute } from "@tanstack/react-router";
import { KisanOneApp } from "@/components/kisan-one";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "KisanOne | Smart Procurement Orchestration" },
      { name: "description", content: "KisanOne coordinates procurement capacity, farmer arrivals, live queues, traceability and payments." },
      { property: "og:title", content: "KisanOne | Smart Procurement Orchestration" },
      { property: "og:description", content: "One Platform. One Process. One Farmer. A capacity-intelligent procurement platform." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  return <KisanOneApp />;
}
