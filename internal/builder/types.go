package builder

import "strings"

// StringSlice is a flag.Value that accumulates multiple values
type StringSlice []string

func (s *StringSlice) String() string {
	return strings.Join(*s, ",")
}

func (s *StringSlice) Set(v string) error {
	*s = append(*s, v)
	return nil
}

type InstructionType string

const (
	From       InstructionType = "FROM"
	Run        InstructionType = "RUN"
	Cmd        InstructionType = "CMD"
	Entrypoint InstructionType = "ENTRYPOINT"
	Env        InstructionType = "ENV"
	Workdir    InstructionType = "WORKDIR"
	Copy       InstructionType = "COPY"
	Add        InstructionType = "ADD"
	Expose     InstructionType = "EXPOSE"
	Label      InstructionType = "LABEL"
	User       InstructionType = "USER"
	Volume     InstructionType = "VOLUME"
	Shell      InstructionType = "SHELL"
	Arg        InstructionType = "ARG"
	StopSignal InstructionType = "STOPSIGNAL"
	Healthcheck InstructionType = "HEALTHCHECK"
	Maintainer InstructionType = "MAINTAINER"
	OnBuild    InstructionType = "ONBUILD"
)

type Instruction struct {
	Type InstructionType
	Args []string
	Raw  string
}

type BuildConfig struct {
	ContextDir string
	Dockerfile string
	ImageName  string
	Tag        string
	NoCache    bool
	BuildArgs  map[string]string
	Quiet      bool
}
