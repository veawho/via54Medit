package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/veawho/via54Medit/internal/docproc"
)

// docprocCmd runs the clinical-document pipeline.
var docprocCmd = &cobra.Command{
	Use:   "docproc [file]",
	Short: "Extract medical entities from documents (PDF / HTML / text)",
	Long:  `Run a local clinical-document pipeline: extract text, extract medical entities, and summarize into SOAP format.`,
	Example: `medit docproc clinical_note.txt
medit docproc clinical_note.txt --soap`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		provider, err := buildLLM()
		if err != nil {
			return fmt.Errorf("llm provider: %w", err)
		}

		// Build pipeline
		var pipeline *docproc.Pipeline
		if cmd.Flags().Changed("no-soap") {
			pipeline = docproc.NewPipelineWithEntityOnly(provider)
		} else {
			pipeline = docproc.NewPipeline(provider)
		}

		result, err := pipeline.Process(context.Background(), args[0])
		if err != nil {
			return err
		}

		if result.RawText != "" {
			fmt.Fprint(os.Stdout, "\n--- RAW TEXT ---\n")
			fmt.Fprint(os.Stdout, result.RawText)
		}

		if result.Entities != nil {
			fmt.Fprint(os.Stdout, "\n--- ENTITIES ---\n")
			pretty, _ := json.MarshalIndent(result.Entities, "", "  ")
			fmt.Fprint(os.Stdout, string(pretty))
		}

		if result.Soap != nil {
			fmt.Fprint(os.Stdout, "\n--- SOAP ---\n")
			pretty, _ := json.MarshalIndent(result.Soap, "", "  ")
			fmt.Fprint(os.Stdout, string(pretty))
		}

		if len(result.Errors) > 0 {
			fmt.Fprint(os.Stderr, "\n--- ERRORS ---\n")
			for _, e := range result.Errors {
				fmt.Fprintln(os.Stderr, "- "+e)
			}
		}

		return nil
	},
}

func init() {
	docprocCmd.Flags().Bool("no-soap", false, "Skip SOAP summarization, extract entities only")
}
