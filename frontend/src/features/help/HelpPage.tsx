import {
  Alert,
  Box,
  Button,
  Link,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";

const repository = "https://github.com/ude-ewl/DH-COMPASS";
export function HelpPage() {
  useLocale();
  return (
    <Box sx={{ height: "100%", overflow: "auto" }}>
      <Stack
        spacing={3}
        sx={{ maxWidth: 900, mx: "auto", p: { xs: 2, sm: 4 }, pb: 6 }}
      >
        <header>
          <Typography component="h1" variant="h4">
            {tr("About DH-COMPASS")}
          </Typography>
          <Typography sx={{ mt: 1 }} color="text.secondary">
            {tr(
              "DH-COMPASS helps explore where a district heating network could be economically attractive. It combines building heat demand, streets and local heat sources, then compares connecting areas to a shared network with decentralized heat supply.",
            )}
          </Typography>
        </header>
        <Alert severity="info">
          {tr(
            "Currently available only for North Rhine-Westphalia (NRW), Germany. The building-demand and heat-potential inputs are specific to NRW; selecting another region is not supported.",
          )}
        </Alert>
        <Paper component="section" variant="outlined" sx={{ p: 3 }}>
          <Typography component="h2" variant="h6">
            {tr("How to use the browser app")}
          </Typography>
          <Stack component="ol" spacing={2} sx={{ pl: 3 }}>
            <li>
              <Typography fontWeight={600}>
                {tr("Select a study area")}
              </Typography>
              <Typography>
                {tr(
                  "Use New run to find a town or address in NRW. Draw a rectangular area on the map, adjust its corners, or enter coordinates under Exact extent. Check the selected area before starting.",
                )}
              </Typography>
            </li>
            <li>
              <Typography fontWeight={600}>
                {tr("Start the calculation")}
              </Typography>
              <Typography>
                {tr(
                  "Select Start calculation. The server checks the inputs, prepares candidate areas and evaluates heat supply and network connections using the configured model assumptions. Follow the progress and map updates; larger areas can take a long time. Closing the browser does not stop an accepted run.",
                )}
              </Typography>
            </li>
            <li>
              <Typography fontWeight={600}>
                {tr("Review and download results")}
              </Typography>
              <Typography>
                {tr(
                  "Open a run from Recent runs. Review the final network, annual heat demand, peak load, costs and heat-supply mix. Use the timeline to inspect recorded connection decisions and Inputs & downloads to access the configuration and available result files.",
                )}
              </Typography>
            </li>
          </Stack>
        </Paper>
        <Paper component="section" variant="outlined" sx={{ p: 3 }}>
          <Typography component="h2" variant="h6">
            {tr("Understanding the map and results")}
          </Typography>
          <Typography sx={{ mt: 1 }}>
            {tr(
              "Green areas are accepted into the heat network; red areas are rejected in favor of decentralized supply. Yellow marks the area currently being evaluated and gray marks pending areas. A connection decision compares the additional annualized central-system and network cost with the decentralized alternative.",
            )}
          </Typography>
          <Typography sx={{ mt: 1 }}>
            {tr(
              "Annual demand and heat production are shown in MWh/a, peak load and installed power in kW, and annualized costs in €/a. Candidate-level values describe one area; final combined results describe the accepted network. Results depend on the input data and assumptions and support an initial planning comparison rather than a detailed engineering design.",
            )}
          </Typography>
        </Paper>
        <Paper component="section" variant="outlined" sx={{ p: 3 }}>
          <Typography component="h2" variant="h6">
            {tr("Change settings or adapt the tool")}
          </Typography>
          <Typography sx={{ my: 1 }}>
            {tr(
              "The browser workflow uses the server's configured defaults. To change technology assumptions, energy prices, cost curves, resource inputs or solver settings, use the GitHub repository and its configuration guide. Scenario TOML files inherit configs/default.toml; changes apply to new runs and do not alter completed results. Adapting the tool beyond NRW also requires suitable regional data and changes to data loading and coverage checks.",
            )}
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <Link href={repository} target="_blank" rel="noopener noreferrer">
              {tr("GitHub repository")}
            </Link>
            <Link
              href={`${repository}/blob/main/docs/configuration.md`}
              target="_blank"
              rel="noopener noreferrer"
            >
              {tr("Configuration guide")}
            </Link>
            <Link
              href={`${repository}/blob/main/docs/methodology.md`}
              target="_blank"
              rel="noopener noreferrer"
            >
              {tr("Methodology")}
            </Link>
          </Stack>
        </Paper>
        <Typography color="text.secondary">
          {tr(
            "Choose English or Deutsch in the header to switch the interface language. Your browser remembers the selection; the study area, run and model settings stay unchanged.",
          )}
        </Typography>
        <Button
          component={RouterLink}
          to="/"
          variant="contained"
          sx={{ alignSelf: "flex-start" }}
        >
          {tr("New run")}
        </Button>
      </Stack>
    </Box>
  );
}
