// SPDX-License-Identifier: AGPL-3.0-only
// Run through validate.py --core so Go's internal-package rules use the selected Core tree.
package main

import (
	"fmt"
	"nex.local/nex/internal/apps"
	"nex.local/nex/internal/protocol"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"go.yaml.in/yaml/v3"
)

func main() {
	paths, err := filepath.Glob(filepath.Join(os.Args[1], "apps", "*", "nex.yaml"))
	must(err)
	for _, path := range paths {
		data, err := os.ReadFile(path)
		must(err)
		p, err := apps.Parse(string(data))
		must(err)
		must(p.ValidateCatalogue())
		s := protocol.AppSettings{Name: p.Name, Copies: 1, PrimaryNetwork: "host", Answers: map[string]string{}}
		for _, f := range p.Fields {
			if f.Kind == protocol.AppFieldStorage {
				s.Storage = append(s.Storage, protocol.AppStorage{Variable: f.Variable, Target: "host"})
			} else {
				s.Answers[f.Variable] = f.Default
				if f.Required && f.Default == "" {
					// Exercise required fields without putting deployable credentials in packages.
					s.Answers[f.Variable] = "catalogue-validation-example"
				}
			}
		}
		facts := apps.ClusterFacts{Hosts: []protocol.AppFormHost{{ID: "lab-host", Enabled: true}}, StorageTargets: []protocol.AppStorageTarget{{ID: "host"}}}
		s = apps.PinHostStorage(p, s, facts)
		if len(s.Storage) > 0 && (len(s.HostIDs) != 1 || s.HostIDs[0] != "lab-host") {
			panic("local storage was not pinned to one host: " + path)
		}
		if problems := apps.Check(p, s, facts); len(problems) > 0 {
			panic(fmt.Sprintf("%s: %v", path, problems))
		}
		rendered, err := apps.Render(apps.RenderInput{Compose: string(data), AppID: "00000000-0000-4000-8000-000000000001", Settings: s, Hosts: s.HostIDs})
		must(err)
		if strings.Contains(strings.ReplaceAll(rendered, "$$", ""), "${") {
			panic("unresolved fields: " + path)
		}
		checkPlatform(string(data), p, s, facts, rendered)
		for _, f := range p.Fields {
			if !f.Required {
				continue
			}
			answer := s.Answers[f.Variable]
			delete(s.Answers, f.Variable)
			if len(apps.Check(p, s, facts)) == 0 {
				panic("missing required setting accepted: " + path + ": " + f.Variable)
			}
			if _, err := apps.Render(apps.RenderInput{Compose: string(data), AppID: "00000000-0000-4000-8000-000000000001", Settings: s, Hosts: s.HostIDs}); err == nil {
				panic("missing required setting rendered: " + path + ": " + f.Variable)
			}
			s.Answers[f.Variable] = answer
		}
		checkCopies(string(data), p, s)
		if len(s.Storage) > 0 {
			s.Storage = nil
			if _, err = apps.Render(apps.RenderInput{Compose: string(data), AppID: "00000000-0000-4000-8000-000000000001", Settings: s, Hosts: s.HostIDs}); err == nil {
				panic("missing storage accepted: " + path)
			}
		}
		fmt.Println(filepath.Base(filepath.Dir(path)) + ": Core settings, storage, networking and replica checks passed")
	}
}

type renderedService struct {
	Volumes  []string
	Networks map[string]struct{ Aliases []string }
	Deploy   struct {
		Replicas       int
		Placement      struct{ Constraints []string }
		UpdateConfig   struct{ Order string } `yaml:"update_config"`
		RollbackConfig struct{ Order string } `yaml:"rollback_config"`
	}
}

func checkCopies(compose string, p apps.Package, s protocol.AppSettings) {
	const id = "00000000-0000-4000-8000-000000000001"
	s.Copies, s.Redundancy = 2, &protocol.AppRedundancy{}
	publish := true
	s.PublishPorts = &publish
	in := apps.RenderInput{Compose: compose, AppID: id, Settings: s, Hosts: s.HostIDs}
	if !p.Scalable {
		if _, err := apps.Render(in); err == nil {
			panic(p.Name + ": multiple copies accepted for single-copy package")
		}
		return
	}
	if len(s.Storage) > 0 {
		blockers := apps.CopiesBlockers(p, s, apps.ClusterFacts{})
		if !slices.ContainsFunc(blockers, func(b protocol.AppCopiesBlocker) bool {
			return b.Code == protocol.AppCopiesHostStorage
		}) {
			panic(p.Name + ": Core did not block multiple copies with host-local folders")
		}
	}
	s.Storage = slices.Clone(s.Storage)
	s.HostIDs = nil
	facts := apps.ClusterFacts{
		Hosts:          []protocol.AppFormHost{{ID: "lab-host", Enabled: true}, {ID: "lab-peer", Enabled: true}},
		StorageTargets: []protocol.AppStorageTarget{{ID: "catalogue-share", Kind: "nfs"}},
	}
	for i := range s.Storage {
		s.Storage[i].Target = "catalogue-share"
		s.Storage[i].Path = strings.ToLower(s.Storage[i].Variable)
	}
	if problems := apps.Check(p, s, facts); len(problems) > 0 {
		panic(fmt.Sprintf("%s: two-copy settings rejected: %v", p.Name, problems))
	}
	in.Settings, in.Hosts = s, []string{"lab-host", "lab-peer"}
	rendered, err := apps.Render(in)
	must(err)
	ports, err := apps.PublishedPorts(rendered, id, s.Name, in.Hosts)
	must(err)
	for _, port := range ports {
		if !port.Ingress {
			panic(p.Name + ": scalable package publishes a port outside the ingress mesh")
		}
	}
	services := decode(rendered).Services
	for _, name := range p.Services {
		want := 1
		if slices.Contains(p.Scale, name) {
			want = 2
		}
		if got := services[apps.RenderedServiceName(id, name)].Deploy.Replicas; got != want {
			panic(fmt.Sprintf("%s: %s has %d replicas, want %d", p.Name, name, got, want))
		}
	}
}

type renderedCompose struct {
	Services map[string]renderedService
	Volumes  map[string]struct{ Name string }
}

func decode(text string) renderedCompose {
	var c renderedCompose
	must(yaml.Unmarshal([]byte(text), &c))
	return c
}

// Check the actual catalogue files through Core's storage and networking transforms,
// rather than treating successful Compose parsing as platform acceptance.
func checkPlatform(compose string, p apps.Package, s protocol.AppSettings, facts apps.ClusterFacts, rendered string) {
	const firstID = "00000000-0000-4000-8000-000000000001"
	const secondID = "10000000-0000-4000-8000-000000000002"
	fail := func(problem string) { panic(p.Name + ": " + problem) }
	base := decode(rendered)
	for _, name := range p.Services {
		svc, ok := base.Services[apps.RenderedServiceName(firstID, name)]
		if !ok {
			fail("rendered service is missing")
		}
		if len(s.Storage) > 0 && !slices.Contains(svc.Deploy.Placement.Constraints, "node.labels.nex.host == lab-host") {
			fail("service is missing its local-storage placement")
		}
		shared, attached := svc.Networks["nex_apps"]
		if attached != (name == p.PrimaryService) {
			fail("shared application network must reach only the primary service")
		}
		if attached && (len(shared.Aliases) != 1 || shared.Aliases[0] != protocol.AppDNSName(s.Name)) {
			fail("primary service does not have the application connection name")
		}
		if !slices.Contains(svc.Networks["default"].Aliases, name) {
			fail("private companion-service DNS alias was lost")
		}
	}
	for _, st := range s.Storage {
		volume := base.Volumes["nex_"+strings.ToLower(st.Variable)]
		if volume.Name != apps.VolumeName(firstID, st.Variable) {
			fail("local folder does not use its Nex-owned volume identity")
		}
	}
	// A second install must not share data or runtime service names with the first.
	second := s
	second.Name += " second"
	other, err := apps.Render(apps.RenderInput{Compose: compose, AppID: secondID, Settings: second, Hosts: s.HostIDs})
	must(err)
	for name := range decode(other).Services {
		if _, exists := base.Services[name]; exists {
			fail("two installations share a runtime service name")
		}
	}
	for _, volume := range decode(other).Volumes {
		for _, original := range base.Volumes {
			if volume.Name == original.Name {
				fail("two installations share a local data volume")
			}
		}
	}
	// Selecting an existing share folder must produce a Core bind, not a literal
	// path from the operator or an accidental new local volume.
	if len(s.Storage) > 0 {
		share := s
		share.Storage = append([]protocol.AppStorage(nil), s.Storage...)
		share.Storage[0].Target, share.Storage[0].Path = "catalogue-share", "existing-folder"
		shareFacts := facts
		shareFacts.StorageTargets = append(append([]protocol.AppStorageTarget(nil), facts.StorageTargets...), protocol.AppStorageTarget{ID: "catalogue-share", Kind: "nfs"})
		if problems := apps.Check(p, share, shareFacts); len(problems) > 0 {
			fail(fmt.Sprint(problems))
		}
		onShare, err := apps.Render(apps.RenderInput{Compose: compose, AppID: firstID, Settings: share, Hosts: s.HostIDs})
		must(err)
		if !strings.Contains(onShare, "/var/lib/nex/apps/binds/"+apps.StorageBindName(firstID, share.Storage[0])+":") {
			fail("share selection did not render to a Core-managed bind")
		}
	}
	// Dedicated primary networks use the application's original listener ports.
	// The checkbox must remove host publication, and sidecars must stay private.
	off := false
	lan := s
	lan.PrimaryNetwork, lan.PublishPorts = "catalogue-network", &off
	lan.Networks = []protocol.AppNetwork{{NetworkID: lan.PrimaryNetwork, Service: p.PrimaryService, Mode: protocol.AppNetworkStatic, Address: "192.0.2.20/24", Gateway: "192.0.2.1"}}
	lanFacts := facts
	lanFacts.Networks = []apps.LANFacts{{AppFormNetwork: protocol.AppFormNetwork{ID: lan.PrimaryNetwork, Kind: "vlan", Hosts: []string{"lab-host"}}}}
	if problems := apps.Check(p, lan, lanFacts); len(problems) > 0 {
		fail(fmt.Sprint(problems))
	}
	onLAN, err := apps.Render(apps.RenderInput{Compose: compose, AppID: firstID, Settings: lan, Hosts: []string{"lab-host"}, Reach: []string{"lab-host"}, LAN: []string{"catalogue-test-network"}})
	must(err)
	ports, err := apps.PublishedPorts(onLAN, firstID, lan.Name, lan.HostIDs)
	must(err)
	if len(ports) != 0 {
		fail("host ports survived the publication checkbox being cleared")
	}
	for _, name := range p.Services {
		svc := decode(onLAN).Services[apps.RenderedServiceName(firstID, name)]
		_, attached := svc.Networks["nex_lan0"]
		if attached != (name == p.PrimaryService) {
			fail("dedicated network must reach only the selected primary service")
		}
		if attached && (svc.Deploy.UpdateConfig.Order != "stop-first" || svc.Deploy.RollbackConfig.Order != "stop-first") {
			fail("dedicated address can be held by overlapping service copies")
		}
	}
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}
